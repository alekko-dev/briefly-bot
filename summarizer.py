import json
import os

from openai import OpenAI

client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_BASE_URL"),  # None = default OpenAI
)
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_TRANSCRIPT_CHARS = 60_000
VERBOSE = False


def _vprint(header: str, content: str) -> None:
    bar = "─" * 60
    print(f"\n{bar}\n[VERBOSE] {header}\n{bar}\n{content}\n{bar}")

# Languages the user understands — no translation needed.
# Comma-separated ISO 639-1 codes, e.g. "en,ru"
NO_TRANSLATE_LANGS: set[str] = set(
    os.environ.get("NO_TRANSLATE_LANGS", "en").split(",")
)

# Language to translate summaries into for all other videos.
# Human-readable name used directly in the LLM prompt.
TARGET_LANG: str = os.environ.get("TARGET_LANG", "English")

SYSTEM_PROMPT = """You are a helpful assistant that creates detailed, well-structured summaries of YouTube video transcripts.

Your summaries should:
1. Start with a brief overview (2-3 sentences)
2. Include a detailed breakdown of main topics discussed
3. Filter out any sponsor messages, subscribe requests, or promotional content
4. Include key timestamps as clickable links for important moments. The transcript contains
   real timestamps in [MM:SS] format at the start of each paragraph — use only these exact
   timestamps, do not invent times that are not in the transcript. Format each link as
   [MM:SS](https://youtu.be/VIDEO_ID?t=SECONDS) where SECONDS is the total seconds of that
   timestamp (e.g. [1:23] → t=83). The video URL is provided in the user message.
5. End with a brief conclusion
6. Use **bold** for section titles instead of Markdown headings (#), and bullet points for readability
7. If the video title contains a question or a promise (e.g. "How to...", "Why...",
   "X will make you..."), make sure the summary explicitly addresses and answers it"""


def summarize(transcript: str, lang_code: str, title: str = "", video_id: str = "") -> str:
    trimmed = transcript[:MAX_TRANSCRIPT_CHARS]
    if lang_code not in NO_TRANSLATE_LANGS:
        extra = f" Translate your response into {TARGET_LANG}."
    else:
        extra = ""
    user_content = f"Transcript:\n{trimmed}"
    if title:
        user_content = f"Title: {title}\n" + user_content
    if video_id:
        user_content = f"Video URL: https://youtu.be/{video_id}\n" + user_content
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + extra},
        {"role": "user", "content": user_content},
    ]
    if VERBOSE:
        _vprint(f"LLM REQUEST  model={MODEL}", json.dumps(messages, ensure_ascii=False, indent=2))

    response = client.chat.completions.create(model=MODEL, messages=messages)
    result = (response.choices[0].message.content or "").strip()

    if VERBOSE:
        usage = response.usage
        usage_str = (
            f"prompt_tokens={usage.prompt_tokens}  "
            f"completion_tokens={usage.completion_tokens}  "
            f"total_tokens={usage.total_tokens}"
        ) if usage else "usage=N/A"
        _vprint(f"LLM RESPONSE  {usage_str}", result)

    return result
