import json
import re
import urllib.parse
import urllib.request
from typing import Optional

# Public Android client settings; we reuse these to inspect caption tracks.
# It's hardcoded inside the YouTube Android app itself and has been widely
# documented by developers who reverse-engineered YouTube's internal API.
API_KEY = "AIzaSyAOgs9M-1-5Zl0s5j-7iYkiT7VYTIzLw"
PLAYER_URL = f"https://www.youtube.com/youtubei/v1/player?key={API_KEY}"
CLIENT_CONTEXT = {
    "client": {
        "clientName": "ANDROID",
        "clientVersion": "19.08.35",
        "hl": "en",
        "gl": "US",
    }
}
TIMEDTEXT_URL = "https://www.youtube.com/api/timedtext"


def video_id_from_input(raw: str) -> str:
    match = re.search(r"(?:v=|/)([0-9A-Za-z_-]{11})", raw)
    if match:
        return match.group(1)
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", raw):
        return raw
    raise ValueError("Could not extract an 11-char YouTube video id.")


def fetch_player(video_id: str) -> dict:
    body = {"videoId": video_id, "context": CLIENT_CONTEXT}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        PLAYER_URL,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "com.google.android.youtube/19.08.35 (Linux; U; Android 13; en_US)",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def pick_caption_track(player: dict, lang: str, kind: str) -> Optional[str]:
    captions = player.get("captions", {}) or {}
    # autoCaptions holds ASR; captionTracks holds manual.
    pools = []
    if kind == "auto":
        pools.append(captions.get("playerCaptionsTracklistRenderer", {}).get("autoCaptions", []))
    if kind == "manual":
        pools.append(captions.get("playerCaptionsTracklistRenderer", {}).get("captionTracks", []))
    # If kind not found, try the other as fallback.
    if not pools or not pools[0]:
        pools.append(captions.get("playerCaptionsTracklistRenderer", {}).get("captionTracks", []))
        pools.append(captions.get("playerCaptionsTracklistRenderer", {}).get("autoCaptions", []))

    for pool in pools:
        for track in pool or []:
            if track.get("languageCode") == lang:
                base_url = track.get("baseUrl")
                if base_url:
                    return base_url
    return None


def fetch_captions_from_url(base_url: str) -> dict:
    # Ensure we ask for JSON structure.
    parsed = urllib.parse.urlparse(base_url)
    q = urllib.parse.parse_qs(parsed.query)
    q["fmt"] = ["json3"]
    new_query = urllib.parse.urlencode(q, doseq=True)
    url = urllib.parse.urlunparse(parsed._replace(query=new_query))
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
        },
    )
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode("utf-8")
    if not body:
        raise RuntimeError("Empty caption response.")
    return json.loads(body)


def cues_from_events(doc: dict) -> list[dict]:
    cues = []
    for ev in doc.get("events", []):
        start_ms = ev.get("tStartMs")
        dur_ms = ev.get("dDurationMs")
        if start_ms is None or dur_ms is None:
            continue
        segs = ev.get("segs") or []
        text = "".join(seg.get("utf8", "") for seg in segs).replace("\n", " ").strip()
        cues.append(
            {
                "start": start_ms / 1000.0,
                "dur": dur_ms / 1000.0,
                "text": text,
            }
        )
    return cues


def get_transcript(video_id: str) -> str:
    """Try en-manual → en-auto → first-available track → raise RuntimeError."""
    player = fetch_player(video_id)
    # Preference order
    for lang, kind in [("en", "manual"), ("en", "auto")]:
        base_url = pick_caption_track(player, lang, kind)
        if base_url:
            doc = fetch_captions_from_url(base_url)
            cues = cues_from_events(doc)
            return " ".join(c["text"] for c in cues if c["text"])
    # Fallback: first available track of any language
    tracks = player.get("captions", {}).get("playerCaptionsTracklistRenderer", {})
    for pool_key in ("captionTracks", "autoCaptions"):
        pool = tracks.get(pool_key) or []
        if pool and pool[0].get("baseUrl"):
            doc = fetch_captions_from_url(pool[0]["baseUrl"])
            cues = cues_from_events(doc)
            return " ".join(c["text"] for c in cues if c["text"])
    raise RuntimeError("No captions available for this video.")
