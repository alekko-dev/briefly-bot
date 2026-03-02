#!/usr/bin/env python3
"""
POC: Fetch and parse YouTube caption tracks (manual or auto-generated)

Purpose:
Python script that fetches caption cues from YouTube videos using the player API and
timedtext API. Used for manual testing of caption availability and structure during
development. Not part of the extension runtime.

What it does:
- Accepts video ID/URL, language code, and kind (manual/auto)
- Calls YouTube player API to get caption track metadata
- Extracts baseUrl for requested language and kind
- Fetches caption data from timedtext API in json3 format
- Parses events into cue objects with start (seconds), dur (seconds), and text
- Outputs cues as JSON array or lists available tracks

Expected output:
- With --list flag: Lists of manual and auto caption tracks
  Example: "- en English (auto-generated) url=https://..."
  Example: "- es Spanish url=https://..."
- Without --list: JSON array of caption cues with start, dur, text fields
  Example: [{"start": 0.0, "dur": 2.5, "text": "Hello world"}, ...]
- Cue times in seconds (converted from milliseconds)
- Text with newlines replaced by spaces
- Limited output if --limit specified (e.g., first 5 cues only)
- Error message if no caption track found for requested language/kind

Usage:
  # List available caption tracks
  python3 scripts/fetch_captions.py <video-id> --list

  # Fetch auto-generated English captions (first 5 cues)
  python3 scripts/fetch_captions.py <video-id> --lang en --kind auto --limit 5

  # Fetch manual Spanish captions (all cues)
  python3 scripts/fetch_captions.py <video-id> --lang es --kind manual

Examples:
  python3 scripts/fetch_captions.py dQw4w9WgXcQ --list
  python3 scripts/fetch_captions.py dQw4w9WgXcQ --lang en --limit 10

Key findings:
- Captions are available in json3 format with millisecond precision
- Auto-generated captions exist for many languages via translation
- Manual captions have better quality when available
- Cue structure is consistent and easy to parse
- Validates the caption fetching approach for phrase-by-phrase playback
"""

import argparse
import json
import re
import sys
import urllib.error
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


def main():
    parser = argparse.ArgumentParser(
        description="Fetch YouTube captions (manual or auto) as JSON cues with start/duration/text."
    )
    parser.add_argument("video", help="YouTube video id or URL.")
    parser.add_argument("--lang", default="en", help="Caption language code (e.g., en, ru, pl).")
    parser.add_argument(
        "--kind",
        choices=["manual", "auto"],
        default="auto",
        help="Caption source: manual (if uploaded) or auto (ASR).",
    )
    parser.add_argument("--limit", type=int, help="Limit number of cues printed.")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available caption tracks (manual + auto) instead of downloading.",
    )
    args = parser.parse_args()

    try:
        video_id = video_id_from_input(args.video)
    except ValueError as exc:
        sys.exit(str(exc))

    try:
        player = fetch_player(video_id)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        sys.exit(f"player request failed: {exc.code} {exc.reason}; {detail[:200]}")

    tracks = player.get("captions", {}).get("playerCaptionsTracklistRenderer", {}) or {}
    manual_tracks = tracks.get("captionTracks", []) or []
    auto_tracks = tracks.get("autoCaptions", []) or []

    if args.list:
        print("Manual captionTracks:")
        for t in manual_tracks:
            print(f"- {t.get('languageCode')} {(t.get('name', {}).get('runs') or [{}])[0].get('text')} url={t.get('baseUrl')}")
        print("Auto autoCaptions:")
        for t in auto_tracks:
            print(f"- {t.get('languageCode')} {(t.get('name', {}).get('runs') or [{}])[0].get('text')} url={t.get('baseUrl')}")
        return

    base_url = pick_caption_track(player, args.lang, args.kind)
    if not base_url:
        sys.exit("No caption track found for requested language/kind.")

    try:
        doc = fetch_captions_from_url(base_url)
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Failed to fetch captions: {exc}")

    cues = cues_from_events(doc)
    if args.limit is not None:
        cues = cues[: args.limit]

    print(json.dumps(cues, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
