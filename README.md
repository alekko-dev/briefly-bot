# Briefly Bot

A personal Telegram bot that summarizes YouTube videos. Share a YouTube URL → get a concise AI-generated summary.

## How it works

1. You send a YouTube URL to the bot in Telegram
2. Bot fetches the video's captions via the YouTube Android API (no API key required)
3. Captions are sent to an LLM (OpenAI or compatible) for summarization
4. Bot replies with a 3–5 bullet point summary

Caption track preference: English manual → English auto-generated → first available track in any language.

## Project structure

```
briefly-bot/
├── captions.py          # YouTube caption fetching + transcript extraction
├── summarizer.py        # LLM summarization via OpenAI-compatible API
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
| Send a YouTube URL | Bot replies "⏳ Fetching captions..." then edits with summary |
| Video with no English captions | Bot uses first available language track |
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
