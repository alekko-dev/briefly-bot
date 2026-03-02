import logging
import os
import re

from telegram import Update
from telegram.ext import Application, MessageHandler, filters

from captions import get_transcript, video_id_from_input
from summarizer import summarize

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER_ID = int(os.environ["TELEGRAM_OWNER_ID"])

YOUTUBE_RE = re.compile(r"https?://(?:www\.)?(?:youtube\.com/\S+|youtu\.be/\S+)")


async def handle_message(update: Update, context) -> None:
    if update.effective_user.id != OWNER_ID:
        return

    text = update.message.text or ""
    url_match = YOUTUBE_RE.search(text)
    if not url_match:
        return

    msg = await update.message.reply_text("⏳ Fetching captions...")
    try:
        video_id = video_id_from_input(url_match.group(0))
        transcript = get_transcript(video_id)
        summary = summarize(transcript)
        await msg.edit_text(summary)
    except RuntimeError as e:
        await msg.edit_text(f"❌ {e}")
    except Exception:
        logger.exception("Unexpected error handling message")
        await msg.edit_text("❌ Something went wrong. Try again.")


def main() -> None:
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Application started")
    app.run_polling()


if __name__ == "__main__":
    main()
