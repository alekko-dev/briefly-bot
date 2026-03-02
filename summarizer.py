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

SYSTEM_PROMPT = """You are a helpful assistant that creates detailed, well-structured summaries of YouTube video transcripts.

Your summaries should:
1. Start with a brief overview (2-3 sentences)
2. Include a detailed breakdown of main topics discussed
3. Filter out any sponsor messages, subscribe requests, or promotional content
4. Include key timestamps in markdown link format like [12:34] for important moments
5. End with a brief conclusion
6. Use clear headings and bullet points for readability
7. If the video title contains a question or a promise (e.g. "How to...", "Why...",
   "X will make you..."), make sure the summary explicitly addresses and answers it

Format timestamps as clickable links using the format: [MM:SS] or [HH:MM:SS]"""


def summarize(transcript: str, lang_code: str, title: str = "") -> str:
    trimmed = transcript[:MAX_TRANSCRIPT_CHARS]
    if lang_code not in NO_TRANSLATE_LANGS:
        extra = f" Translate your response into {TARGET_LANG}."
    else:
        extra = ""
    user_content = f"Transcript:\n{trimmed}"
    if title:
        user_content = f"Title: {title}\nTranscript:\n{user_content}"
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + extra},
            {"role": "user", "content": user_content},
        ],
    )
    return (response.choices[0].message.content or "").strip()
