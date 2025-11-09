# main.py
import os
import time
import signal
import logging
import asyncio
from pathlib import Path
from telegram import Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

LOG = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEFAULT_CHAT_ID = os.getenv("CHAT_ID")  # optional

# Simple in-memory state (for /record flow)
user_state = {}
SHUTDOWN = False

async def start_cmd(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Namaskara! Use /record to start.\nFlow: /record -> send URL -> send minutes."
    )

async def record_cmd(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = {"step": "ask_url"}
    await update.message.reply_text("🎥 Send the stream URL (m3u8/RTSP/HTTP):")

async def handle_message(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    import subprocess, asyncio
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()

    if user_id not in user_state:
        await update.message.reply_text("❗ Please type /record first.")
        return

    step = user_state[user_id].get("step")
    if step == "ask_url":
        user_state[user_id]["stream_url"] = text
        user_state[user_id]["step"] = "ask_time"
        await update.message.reply_text("⏱️ How many minutes to record? (integer)")
        return

    if step == "ask_time":
        try:
            minutes = int(text)
            if minutes <= 0:
                raise ValueError()
        except Exception:
            await update.message.reply_text("⚠️ Enter a positive integer for minutes.")
            return

        stream_url = user_state[user_id]["stream_url"]
        await update.message.reply_text(f"🎬 Recording {minutes} minute(s) from: {stream_url}")

        out_dir = Path("recordings")
        out_dir.mkdir(exist_ok=True)
        filename = f"record_{user_id}_{int(time.time())}.mp4"
        output_path = out_dir / filename

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", stream_url,
            "-t", str(minutes * 60), "-c", "copy", str(output_path)
        ]

        # Run blocking ffmpeg in thread to avoid blocking PTB event loop
        def run_ffmpeg():
            LOG.info("Running ffmpeg: %s", " ".join(ffmpeg_cmd))
            subprocess.run(ffmpeg_cmd, check=True)

        try:
            await update.message.reply_text("⏳ Starting recording (ffmpeg)...")
            await asyncio.to_thread(run_ffmpeg)
        except Exception as e:
            LOG.exception("Recording failed")
            await update.message.reply_text(f"❌ Recording failed: {e}")
            user_state.pop(user_id, None)
            # cleanup partial file
            try:
                if output_path.exists():
                    output_path.unlink()
            except Exception:
                pass
            return

        await update.message.reply_text("📤 Uploading to Telegram...")
        bot = Bot(token=BOT_TOKEN)
        target_chat = DEFAULT_CHAT_ID or update.effective_chat.id
        try:
            with open(output_path, "rb") as f:
                await bot.send_video(chat_id=target_chat, video=f, caption=f"✅ Recording complete ({minutes} min)")
        except Exception as e:
            LOG.exception("Upload failed")
            await update.message.reply_text(f"❌ Upload failed: {e}")
        finally:
            try:
                output_path.unlink()
            except Exception:
                pass

        user_state.pop(user_id, None)
        await update.message.reply_text("✅ Done!")

def build_app():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("record", record_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app

# Graceful shutdown handler
def _signal_handler(signum, frame):
    global SHUTDOWN
    LOG.info("Signal %s received, shutting down...", signum)
    SHUTDOWN = True

signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)

def run_worker_loop():
    """Main loop: run bot, restart on unhandled exceptions."""
    restart_delay = 5
    while not SHUTDOWN:
        try:
            LOG.info("Starting Telegram bot...")
            app = build_app()
            # run_polling blocks until stopped or exception
            app.run_polling()
            LOG.warning("app.run_polling() exited normally")
        except Exception as e:
            LOG.exception("Bot crashed with exception; will restart in %s seconds", restart_delay)
            # brief pause before restart
            for i in range(restart_delay):
                if SHUTDOWN:
                    break
                time.sleep(1)
            continue
        # If here, the bot stopped without exception. Sleep a bit and restart unless shutting down.
        if not SHUTDOWN:
            LOG.warning("Bot stopped unexpectedly without exception — restarting after %s s", restart_delay)
            time.sleep(restart_delay)

    LOG.info("Worker loop finished, exiting process.")

if __name__ == "__main__":
    if not BOT_TOKEN:
        LOG.error("BOT_TOKEN environment variable not set. Exiting.")
        exit(1)

    # Ensure recordings dir exists
    Path("recordings").mkdir(exist_ok=True)

    try:
        run_worker_loop()
    except Exception:
        LOG.exception("Fatal error in main")
        exit(1)
    LOG.info("Process exiting")
