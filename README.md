# Briefly Bot

A personal Telegram bot that summarizes YouTube videos. Share a YouTube URL → get a concise AI-generated summary, a detailed retelling, or answers to specific questions.

## How it works

1. You send a YouTube URL to the bot in Telegram (optionally with extra text)
2. Bot fetches the video's captions via youtube-transcript-api (no YouTube API key required)
3. Captions are sent to an LLM (OpenAI or compatible)
4. Bot replies with a structured response including clickable timestamp links

Caption track preference: manual subtitles → auto-generated captions, original video language first within each group.

### Modes

| What you send | Mode | Description |
|---|---|---|
| `<url>` | Summary | Concise summary with sections and key timestamps |
| `<url> detail` | Detail | Comprehensive retelling covering all points the author makes, in order |
| `<url> <any question>` | Q&A | Direct answer to your question, with supporting quotes and timestamps |

Detail mode also accepts: `detailed`, `full`, `retell`, `long`.

## Project structure

```
briefly-bot/
├── captions.py          # YouTube caption fetching + transcript extraction
├── llm.py               # LLM calls via OpenAI-compatible API (summarize, ask_question)
├── bot.py               # Telegram bot entry point
├── requirements.txt
├── .env.example
├── Procfile             # Railway deployment
└── scripts/
    └── poc_fetch_captions.py   # Original POC script (reference only)
```

## Setup

### Prerequisites

- Python 3.11+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your Telegram numeric user ID (get it from [@userinfobot](https://t.me/userinfobot))
- An OpenAI API key (or a compatible endpoint, e.g. local Ollama)

### Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env and fill in your values
```

`.env` fields:

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | From @BotFather |
| `TELEGRAM_OWNER_ID` | Yes | Your Telegram numeric user ID |
| `OPENAI_API_KEY` | Yes | API key for LLM endpoint |
| `OPENAI_BASE_URL` | No | Custom endpoint (omit for OpenAI default) |
| `OPENAI_MODEL` | No | Model name (default: `gpt-4o-mini`) |
| `NO_TRANSLATE_LANGS` | No | Comma-separated ISO 639-1 codes to not translate (default: `en`) |
| `TARGET_LANG` | No | Language to translate summaries into (default: `English`) |

### Telegram numeric user ID (not your @username)

1. Start a chat with your bot
2. Send a message
3. Call: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Look for: `"from": { "id": 123456789 }`
5. That is your user ID.

## Development

Run locally:

```bash
source .venv/bin/activate
python bot.py
```

The bot uses polling — no webhook or public URL needed for local development.

### Testing the caption fetcher

The POC script can be used to inspect caption availability for any video:

```bash
# List available caption tracks
python scripts/poc_fetch_captions.py <video-id> --list

# Fetch auto-generated English captions (first 10 cues)
python scripts/poc_fetch_captions.py <video-id> --lang en --kind auto --limit 10
```

### Manual test scenarios

| Scenario | Expected result |
|---|---|
| Send a YouTube URL alone | Concise summary with sections and timestamps |
| Send `<url> detail` | Comprehensive retelling of all points in order |
| Send `<url> What does the speaker say about X?` | Direct answer with relevant quotes and timestamps |
| Question text before the URL (`What about X? <url>`) | Q&A mode — full non-URL text is used as the question |
| Send `<url> Is this too detailed?` | Q&A mode (keyword match is exact; phrase is treated as a question) |
| Video in a foreign language | Fetches native-language captions and translates the response |
| Video with no captions at all | Bot replies "❌ No captions available for this video." |
| Message sent from another account | Bot ignores it silently |
| Non-YouTube message | Bot ignores it silently |

## Deployment (Railway)

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
3. Select your repo
4. In **Variables**, add all required env vars from `.env.example`
5. Railway detects the `Procfile` and runs `python bot.py` as a worker process

No port binding is needed — the bot uses polling, not webhooks. It runs continuously within Railway's free $5/month credit (~500 hours/month).

### Checking logs

```bash
railway logs
```

Look for `Application started` to confirm the bot is running.

## Architecture

### Caption fetching (`captions.py`)

`youtube-transcript-api` fetches caption tracks directly from YouTube's timedtext API. Track selection prefers manual subtitles over auto-generated; within each group the library returns the video's original language first, so no explicit language detection is needed. The video title is fetched separately via YouTube's public oEmbed endpoint. Caption cues are grouped into 30-second buckets and prefixed with `[MM:SS]` timestamps, giving the LLM concrete time references to build clickable deep-links from.

### LLM integration (`llm.py`)

Calls any OpenAI-compatible endpoint via the `openai` library (`OPENAI_BASE_URL` selects the backend). The user message contains the video title, URL, and timestamped transcript. All three modes share the same transport layer; they differ only in system prompt and user content:

- **Summary** — instructs the LLM to produce a concise structured overview with bold section titles and key timestamps.
- **Detail** — instructs the LLM to cover every point the author makes in order, in narrative paragraph style, without skipping or compressing arguments.
- **Q&A** — prepends the user's question to the transcript; instructs the LLM to answer directly, quote relevant passages, and say clearly if the video doesn't address the question.

All modes translate the response into `TARGET_LANG` when the video language is not in `NO_TRANSLATE_LANGS`. Transcripts are truncated at 120,000 chars (≈ 1–1.5 h of speech); a warning is appended when truncation occurs.

### Telegram rendering (`bot.py`)

The LLM returns Markdown. Telegram's `parse_mode="HTML"` accepts only `<b>`, `<i>`, `<s>`, `<code>`, `<pre>`, `<blockquote>`, and `<a>`. A custom mistune renderer (`TelegramRenderer`) maps Markdown constructs to that subset: headings → `<b>`, lists → `•` bullet characters, line breaks → `\n\n`.

### Design decisions

**youtube-transcript-api instead of yt-dlp.** The original implementation used the YouTube Android API directly (hardcoded client version and API key). YouTube's changing requirements broke it repeatedly. yt-dlp was introduced to absorb those changes, but its caption URL fetching returns empty responses for live streams and recent VODs — the signed CDN URLs expire or are not yet populated when the metadata is extracted. `youtube-transcript-api` fetches captions through a separate, more reliable path (YouTube's timedtext API) and handles live streams correctly.

**Native-language captions, LLM translates.** An English-first caption selection strategy caused HTTP 429 errors: YouTube rate-limits translated caption endpoints. Fetching the original-language track is reliable, and delegating translation to the LLM produces better results anyway.

