import os

from openai import OpenAI

client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_BASE_URL"),  # None = default OpenAI
)
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_TRANSCRIPT_CHARS = 60_000

SYSTEM_PROMPT = """You are a concise video summarizer. Given a YouTube video transcript,
write a clear, structured summary in 3-5 bullet points. Focus on the key ideas and takeaways.
Use plain text, no markdown headers."""


def summarize(transcript: str) -> str:
    trimmed = transcript[:MAX_TRANSCRIPT_CHARS]
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Transcript:\n{trimmed}"},
        ],
    )
    return response.choices[0].message.content.strip()
