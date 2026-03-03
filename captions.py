import json
import re
import urllib.request

from youtube_transcript_api import (
    NoTranscriptFound,
    PoTokenRequired,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)


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


def _fetch_title(video_id: str) -> str:
    """Fetch video title via YouTube's public oEmbed endpoint."""
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8")).get("title", "")
    except Exception:
        return ""


def get_transcript(video_id: str) -> tuple[str, str, str]:
    """Return (transcript_text, lang_code, title).

    Prefers manual subtitles over auto-generated. Within each group the
    library returns the video's original language first, so no explicit
    language-code detection is needed.
    """
    title = _fetch_title(video_id)

    api = YouTubeTranscriptApi()
    try:
        transcript_list = api.list(video_id)
    except TranscriptsDisabled:
        raise RuntimeError("No captions available for this video.")
    except Exception as exc:
        raise RuntimeError("No captions available for this video.") from exc

    for finder in (
        lambda tl: next((t for t in tl if not t.is_generated), None),  # any manual
        lambda tl: next(iter(tl), None),                                # any auto-generated
    ):
        try:
            transcript = finder(transcript_list)
        except NoTranscriptFound:
            continue
        if transcript is None:
            continue

        try:
            fetched = transcript.fetch()
        except (PoTokenRequired, Exception):
            continue

        BUCKET_MS = 30_000  # 30-second grouping windows
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
            f"[{_ms_to_mmss(first_ms)}] {' '.join(cues)}"
            for _, (first_ms, cues) in sorted(buckets.items())
        ]
        text = "\n".join(lines)
        if text:
            return text, transcript.language_code, title

    raise RuntimeError("No captions available for this video.")
