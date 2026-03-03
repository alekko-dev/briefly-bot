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
import llm
from llm import summarize, ask_question

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
DETAIL_KEYWORDS = {"detail", "detailed", "full", "retell", "long"}


def _sanitize_links(html: str, video_id: str) -> str:
    """Strip any links that don't point to the expected video's timestamps."""
    allowed = re.compile(r"^https://youtu\.be/" + re.escape(video_id) + r"\?t=\d+$")

    def _check(m: re.Match) -> str:
        url, text = m.group(1), m.group(2)
        return m.group(0) if allowed.match(url) else text

    return re.sub(r'<a href="([^"]*)">(.*?)</a>', _check, html, flags=re.DOTALL)


async def handle_message(update: Update, context) -> None:
    if update.effective_user.id != OWNER_ID:
        return

    text = update.message.text or ""
    url_match = YOUTUBE_RE.search(text)
    if not url_match:
        return

    url = url_match.group(0)
    rest = (text[:url_match.start()] + text[url_match.end():])
    rest = " ".join(rest.split())  # collapse whitespace

    if not rest:
        mode, question = "summary", None
    elif rest.lower() in DETAIL_KEYWORDS:
        mode, question = "detail", None
    else:
        mode, question = "qa", rest

    msg = await update.message.reply_text("⏳ Fetching captions...")
    try:
        video_id = video_id_from_input(url)
        transcript, lang_code, title = get_transcript(video_id)
        if VERBOSE:
            _vprint(
                f"TRANSCRIPT  lang={lang_code}  title={title!r}  chars={len(transcript)}  mode={mode}",
                transcript[:3000] + (" …[truncated]" if len(transcript) > 3000 else ""),
            )
        if mode == "qa":
            await msg.edit_text("⏳ Answering your question...")
            result = ask_question(transcript, lang_code, title, video_id, question)
        elif mode == "detail":
            await msg.edit_text("⏳ Writing detailed retelling...")
            result = summarize(transcript, lang_code, title, video_id, mode="detail")
        else:
            await msg.edit_text("⏳ Summarizing...")
            result = summarize(transcript, lang_code, title, video_id)
        rendered = _sanitize_links(_md(result).strip(), video_id)
        await msg.edit_text(rendered, parse_mode="HTML")
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
    llm.VERBOSE = args.verbose

    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Application started%s", " [VERBOSE]" if VERBOSE else "")
    app.run_polling()


if __name__ == "__main__":
    main()
