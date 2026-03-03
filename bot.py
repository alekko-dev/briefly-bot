import argparse
import logging
import os
import re

import mistune


class TelegramRenderer(mistune.HTMLRenderer):
    def heading(self, text, level, **attrs):
        return f"<b>{text}</b>\n\n"

    def paragraph(self, text):
        return f"{text}\n\n"

    def list(self, text, ordered, **attrs):
        return text + "\n"

    def list_item(self, text, **attrs):
        return f"• {text.strip()}\n"

    def block_code(self, code, **attrs):
        return f"<pre>{code}</pre>\n\n"

    def block_quote(self, text):
        return f"<blockquote>{text.strip()}</blockquote>\n\n"

    def thematic_break(self, **attrs):
        return "\n"

    def strong(self, text):
        return f"<b>{text}</b>"

    def emphasis(self, text):
        return f"<i>{text}</i>"

    def strikethrough(self, text):
        return f"<s>{text}</s>"

    def link(self, text, url, title=None, **attrs):
        return f'<a href="{url}">{text}</a>'

    def codespan(self, code):
        return f"<code>{code}</code>"

    def linebreak(self):
        return "\n\n"

    def image(self, text, url, title=None, **attrs):
        return text or ""


_md = mistune.create_markdown(renderer=TelegramRenderer(), plugins=["strikethrough"])

from dotenv import load_dotenv

load_dotenv()

from telegram import Update
from telegram.ext import Application, MessageHandler, filters

from captions import get_transcript, video_id_from_input
import summarizer
from summarizer import summarize

VERBOSE = False


def _vprint(header: str, content: str) -> None:
    bar = "─" * 60
    print(f"\n{bar}\n[VERBOSE] {header}\n{bar}\n{content}\n{bar}")

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
        transcript, lang_code, title = get_transcript(video_id)
        if VERBOSE:
            _vprint(
                f"TRANSCRIPT  lang={lang_code}  title={title!r}  chars={len(transcript)}",
                transcript[:3000] + (" …[truncated]" if len(transcript) > 3000 else ""),
            )
        summary = summarize(transcript, lang_code, title, video_id)
        await msg.edit_text(_md(summary).strip(), parse_mode="HTML")
    except RuntimeError as e:
        await msg.edit_text(f"❌ {e}")
    except Exception:
        logger.exception("Unexpected error handling message")
        await msg.edit_text("❌ Something went wrong. Try again.")


def main() -> None:
    global VERBOSE
    parser = argparse.ArgumentParser(description="Briefly Telegram bot")
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print captions, LLM request/response, and other debug info to stdout",
    )
    args = parser.parse_args()
    VERBOSE = args.verbose
    summarizer.VERBOSE = args.verbose

    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Application started%s", " [VERBOSE]" if VERBOSE else "")
    app.run_polling()


if __name__ == "__main__":
    main()
