import os

from openai import OpenAI

client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_BASE_URL"),  # None = default OpenAI
)
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_TRANSCRIPT_CHARS = 60_000

# Languages the user understands — no translation needed.
# Comma-separated ISO 639-1 codes, e.g. "en,ru"
NO_TRANSLATE_LANGS: set[str] = set(
    os.environ.get("NO_TRANSLATE_LANGS", "en").split(",")
)

# Language to translate summaries into for all other videos.
# Human-readable name used directly in the LLM prompt.
TARGET_LANG: str = os.environ.get("TARGET_LANG", "English")

SYSTEM_PROMPT = """You are a concise video summarizer. Given a YouTube video transcript,
write a clear, structured summary in 3-5 bullet points. Focus on the key ideas and takeaways.
Use plain text, no markdown headers."""


def summarize(transcript: str, lang_code: str) -> str:
    trimmed = transcript[:MAX_TRANSCRIPT_CHARS]
    if lang_code not in NO_TRANSLATE_LANGS:
        extra = f" Translate your response into {TARGET_LANG}."
    else:
        extra = ""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + extra},
            {"role": "user", "content": f"Transcript:\n{trimmed}"},
        ],
    )
    return (response.choices[0].message.content or "").strip()
