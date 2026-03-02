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


def _ms_to_mmss(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


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

        BUCKET_MS = 30_000  # 30-second grouping windows

        buckets: dict[int, tuple[int, list[str]]] = {}  # bucket_idx -> (first_ms, [cue, ...])
        for ev in doc.get("events", []):
            t = ev.get("tStartMs")
            if t is None or ev.get("dDurationMs") is None:
                continue
            cue = "".join(seg.get("utf8", "") for seg in ev.get("segs") or []).replace("\n", " ").strip()
            if not cue:
                continue
            idx = t // BUCKET_MS
            if idx not in buckets:
                buckets[idx] = (t, [])
            buckets[idx][1].append(cue)

        lines = [
            f"[{_ms_to_mmss(first_ms)}] {' '.join(cues)}"
            for _, (first_ms, cues) in sorted(buckets.items())
        ]
        text = "\n".join(lines)
        if text:
            return text, lang, title

    raise RuntimeError("No captions available for this video.")
