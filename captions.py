import json
import re
import urllib.request

import yt_dlp


def video_id_from_input(raw: str) -> str:
    match = re.search(r"(?:v=|/)([0-9A-Za-z_-]{11})", raw)
    if match:
        return match.group(1)
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", raw):
        return raw
    raise ValueError("Could not extract an 11-char YouTube video id.")


def get_transcript(video_id: str) -> tuple[str, str, str]:
    """Return (transcript_text, lang_code, title). Prefers manual over auto, English over others."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    title = info.get("title") or ""

    for pool in (info.get("subtitles") or {}, info.get("automatic_captions") or {}):
        if not pool:
            continue
        lang = "en" if "en" in pool else next(iter(pool), None)
        if not lang:
            continue
        formats = pool[lang]
        fmt = next((f for f in formats if f.get("ext") == "json3"), None) or (formats[0] if formats else None)
        if not fmt or not fmt.get("url"):
            continue

        req = urllib.request.Request(fmt["url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp:
            doc = json.loads(resp.read().decode("utf-8"))

        cues = [
            "".join(seg.get("utf8", "") for seg in ev.get("segs") or []).replace("\n", " ").strip()
            for ev in doc.get("events", [])
            if ev.get("tStartMs") is not None and ev.get("dDurationMs") is not None
        ]
        text = " ".join(c for c in cues if c)
        if text:
            return text, lang, title

    raise RuntimeError("No captions available for this video.")
