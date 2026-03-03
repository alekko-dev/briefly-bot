#!/usr/bin/env python3
"""
POC: Fetch YouTube captions via yt-dlp (mirrors captions.py logic).

Prints available caption tracks, then attempts to download the transcript
using the same format-priority logic as captions.py. Useful for diagnosing
why a specific video fails (empty response, missing json3, etc.).

Note: yt-dlp is no longer in requirements.txt (replaced by youtube-transcript-api in
production). Install it manually for dev use: pip install yt-dlp

Usage:
  python3 scripts/poc_yt_dlp_captions.py <video-id-or-url>
  python3 scripts/poc_yt_dlp_captions.py <video-id-or-url> --list
  python3 scripts/poc_yt_dlp_captions.py <video-id-or-url> --limit 10

Examples:
  python3 scripts/poc_yt_dlp_captions.py 4UvfPmlCKWQ
  python3 scripts/poc_yt_dlp_captions.py "https://www.youtube.com/live/4UvfPmlCKWQ" --list
"""

import argparse
import json
import re
import sys

import yt_dlp


def video_id_from_input(raw: str) -> str:
    match = re.search(r"(?:v=|/)([0-9A-Za-z_-]{11})", raw)
    if match:
        return match.group(1)
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", raw):
        return raw
    raise ValueError("Could not extract an 11-char YouTube video id.")


def ms_to_mmss(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


def parse_json3(content: str) -> list[dict]:
    doc = json.loads(content)
    cues = []
    for ev in doc.get("events", []):
        t = ev.get("tStartMs")
        dur = ev.get("dDurationMs")
        if t is None or dur is None:
            continue
        text = "".join(seg.get("utf8", "") for seg in ev.get("segs") or []).replace("\n", " ").strip()
        if text:
            cues.append({"start_ms": t, "dur_ms": dur, "text": text})
    return cues


_VTT_TS = re.compile(r"(\d+):(\d+):(\d+)[.,](\d+)\s+-->")
_VTT_TAG = re.compile(r"<[^>]+>")


def parse_vtt(content: str) -> list[dict]:
    cues = []
    current_ms = None
    for line in content.splitlines():
        line = line.strip()
        m = _VTT_TS.match(line)
        if m:
            h, mm, s, frac = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            current_ms = (h * 3600 + mm * 60 + s) * 1000 + int(frac[:3].ljust(3, "0"))
            continue
        if not line or "-->" in line or line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        if current_ms is None:
            continue
        text = _VTT_TAG.sub("", line).strip()
        if text:
            cues.append({"start_ms": current_ms, "text": text})
    return cues


def fmt_priority(f: dict) -> int:
    ext = f.get("ext", "")
    return 0 if ext == "json3" else (1 if ext == "vtt" else 2)


def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube captions via yt-dlp.")
    parser.add_argument("video", help="YouTube video id or URL.")
    parser.add_argument("--list", action="store_true", help="List available tracks only.")
    parser.add_argument("--limit", type=int, help="Limit printed lines of transcript.")
    args = parser.parse_args()

    try:
        video_id = video_id_from_input(args.video)
    except ValueError as exc:
        sys.exit(str(exc))

    url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"video_id: {video_id}", flush=True)

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "socket_timeout": 30}) as ydl:
        info = ydl.extract_info(url, download=False)

    title = info.get("title") or ""
    orig_lang = info.get("language") or ""
    print(f"title:    {title}")
    print(f"lang:     {orig_lang or '(not set)'}")
    print()

    subtitles = info.get("subtitles") or {}
    auto_captions = info.get("automatic_captions") or {}

    print(f"Manual subtitle langs:    {list(subtitles.keys()) or '(none)'}")
    print(f"Auto-caption langs:       {list(auto_captions.keys()) or '(none)'}")
    print()

    for pool_name, pool in [("subtitles", subtitles), ("automatic_captions", auto_captions)]:
        if not pool:
            continue
        lang = orig_lang if (orig_lang and orig_lang in pool) else next(iter(pool), None)
        if not lang:
            continue
        formats = pool[lang]
        print(f"[{pool_name}] lang={lang}, formats available:")
        for f in formats:
            print(f"  ext={f.get('ext'):<8} url={'(present)' if f.get('url') else '(missing)'}")

        if args.list:
            continue

        print(f"\nAttempting download from [{pool_name}] lang={lang} ...")
        for fmt in sorted(formats, key=fmt_priority):
            if not fmt.get("url"):
                print(f"  skip ext={fmt.get('ext')}: no url")
                continue
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl2:
                try:
                    raw = ydl2.urlopen(fmt["url"]).read()
                except Exception as exc:
                    print(f"  ext={fmt.get('ext')}: urlopen failed: {exc}")
                    continue

            print(f"  ext={fmt.get('ext')}: response size={len(raw)} bytes")
            if not raw:
                print("  -> empty response, skipping")
                continue

            decoded = raw.decode("utf-8")
            try:
                if fmt.get("ext") == "json3":
                    cues = parse_json3(decoded)
                else:
                    cues = parse_vtt(decoded)
            except Exception as exc:
                print(f"  -> parse error: {exc}")
                continue

            print(f"  -> parsed {len(cues)} cues\n")

            limit = args.limit or len(cues)
            for cue in cues[:limit]:
                ts = ms_to_mmss(cue["start_ms"])
                print(f"[{ts}] {cue['text']}")
            if args.limit and len(cues) > args.limit:
                print(f"... ({len(cues) - args.limit} more cues)")

            sys.exit(0)

        print("  -> all formats exhausted, no transcript obtained from this pool\n")

    print("No transcript obtained via yt-dlp.")


if __name__ == "__main__":
    main()
