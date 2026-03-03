#!/usr/bin/env python3
"""
POC: Fetch YouTube captions via youtube-transcript-api.

Uses a completely different fetch path from yt-dlp — goes directly to
YouTube's timedtext API. Useful for videos where yt-dlp caption URLs
return empty responses (e.g. live streams / recent VODs).

Install:  pip install "youtube-transcript-api>=1.0"

Usage:
  python3 scripts/poc_transcript_api.py <video-id-or-url>
  python3 scripts/poc_transcript_api.py <video-id-or-url> --list
  python3 scripts/poc_transcript_api.py <video-id-or-url> --limit 10
  python3 scripts/poc_transcript_api.py <video-id-or-url> --lang ru

Examples:
  python3 scripts/poc_transcript_api.py 4UvfPmlCKWQ
  python3 scripts/poc_transcript_api.py "https://www.youtube.com/live/4UvfPmlCKWQ" --list
"""

import argparse
import re
import sys


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


def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube captions via youtube-transcript-api.")
    parser.add_argument("video", help="YouTube video id or URL.")
    parser.add_argument("--list", action="store_true", help="List available transcripts only.")
    parser.add_argument("--lang", default=None, help="Prefer this language code (e.g. en, ru).")
    parser.add_argument("--limit", type=int, help="Limit printed lines of transcript.")
    args = parser.parse_args()

    try:
        from youtube_transcript_api import (
            YouTubeTranscriptApi,
            NoTranscriptFound,
            TranscriptsDisabled,
            PoTokenRequired,
        )
    except ImportError:
        sys.exit("youtube-transcript-api not installed. Run: pip install 'youtube-transcript-api>=1.0'")

    try:
        video_id = video_id_from_input(args.video)
    except ValueError as exc:
        sys.exit(str(exc))

    print(f"video_id: {video_id}", flush=True)

    api = YouTubeTranscriptApi()

    try:
        transcript_list = api.list(video_id)
    except TranscriptsDisabled:
        sys.exit("Transcripts are disabled for this video.")
    except Exception as exc:
        sys.exit(f"Failed to list transcripts: {exc}")

    print("\nAvailable transcripts:")
    all_transcripts = list(transcript_list)
    for t in all_transcripts:
        kind = "auto-generated" if t.is_generated else "manual"
        print(f"  lang={t.language_code:<8} {kind:<14} name='{t.language}'")

    if args.list:
        return

    print()

    # Pick transcript: requested lang → manual English → any manual → auto English → any
    pref_langs = ([args.lang] if args.lang else []) + ["en", "en-US", "en-GB"]
    transcript = None

    for finder_desc, finder in [
        ("requested/English manual", lambda tl: tl.find_manually_created_transcript(pref_langs)),
        ("any manual",               lambda tl: next((t for t in tl if not t.is_generated), None)),
        ("requested/English auto",   lambda tl: tl.find_generated_transcript(pref_langs)),
        ("any auto",                 lambda tl: next(iter(tl), None)),
    ]:
        try:
            result = finder(transcript_list)
        except NoTranscriptFound:
            result = None
        if result is not None:
            transcript = result
            print(f"Selected: {transcript.language_code} ({finder_desc})")
            break

    if transcript is None:
        sys.exit("No usable transcript found.")

    print(f"Fetching (lang={transcript.language_code}, generated={transcript.is_generated}) ...")
    try:
        fetched = transcript.fetch()
    except PoTokenRequired:
        sys.exit("YouTube requires a PoToken for this video — cannot fetch without browser auth.")
    except Exception as exc:
        sys.exit(f"Fetch failed: {exc}")

    print(f"Fetched {len(fetched)} snippets\n")

    # Bucket into 30-second windows (same logic as captions.py)
    BUCKET_MS = 30_000
    buckets: dict[int, tuple[int, list[str]]] = {}
    for snippet in fetched:
        t_ms = int(snippet.start * 1000)
        cue = snippet.text.replace("\n", " ").strip()
        if not cue:
            continue
        idx = t_ms // BUCKET_MS
        if idx not in buckets:
            buckets[idx] = (t_ms, [])
        buckets[idx][1].append(cue)

    lines = [
        f"[{ms_to_mmss(first_ms)}] {' '.join(cues)}"
        for _, (first_ms, cues) in sorted(buckets.items())
    ]

    limit = args.limit or len(lines)
    for line in lines[:limit]:
        print(line)
    if args.limit and len(lines) > args.limit:
        print(f"... ({len(lines) - args.limit} more lines)")

    print(f"\nTotal bucketed lines: {len(lines)}")
    print(f"Total chars: {sum(len(l) for l in lines)}")


if __name__ == "__main__":
    main()
