#!/usr/bin/env python3
"""
Robust Telegram Live Stream Recorder Bot (main.py)

Features:
- /start and /record flow: user sends stream URL and minutes
- Uses ffmpeg with protocol_whitelist and rw_timeout
- Tries '-c copy' first, falls back to re-encoding (libx264 + aac)
- Async lifecycle using python-telegram-bot Application (no run_polling loop)
- Handles telegram.error.Conflict with retry/backoff
- Graceful shutdown on SIGINT/SIGTERM
- Removes local recordings after successful upload
"""

import os
import asyncio
import signal
import logging
from pathlib import Path
import time
import traceback
import shlex
import subprocess

from telegram import Bot
from telegram.error import Conflict
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# -------------------------
# Configuration & Logging
# -------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEFAULT_CHAT_ID = os.getenv("CHAT_ID")  # optional: if set, uploads go there instead of user chat
RECORDINGS_DIR = Path("recordings")
RECORDINGS_DIR.mkdir(exist_ok=True)

# Backoff settings for Conflict / network issues
INITIAL_BACKOFF = 5
MAX_BACKOFF = 120

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
LOG = logging.getLogger("live-tv-bot")

# State
SHUTDOWN = False
user_state = {}  # simple in-memory state: {user_id: {step, stream_url, duration_minutes}}

# -------------------------
# FFmpeg helpers
# -------------------------
def ffmpeg_cmd_copy(stream_url: str, output_path: str, duration_seconds: int):
    return [
        "ffmpeg",
        "-protocol_whitelist",
        "file,http,https,tcp,tls",
        "-rw_timeout",
        str(15_000_000),  # 15s
        "-y",
        "-i",
        stream_url,
        "-t",
        str(duration_seconds),
        "-c",
        "copy",
        output_path,
    ]


def ffmpeg_cmd_reencode(stream_url: str, output_path: str, duration_seconds: int):
    return [
        "ffmpeg",
        "-protocol_whitelist",
        "file,http,https,tcp,tls",
        "-rw_timeout",
        str(15_000_000),
        "-y",
        "-i",
        stream_url,
        "-t",
        str(duration_seconds),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        output_path,
    ]


def run_subprocess_capture(cmd):
    """
    Run a blocking subprocess, capture stdout/stderr (text).
    Return (returncode, stdout, stderr).
    """
    LOG.info("Running command: %s", shlex.join(cmd))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.returncode, proc.stdout, proc.stderr


# -------------------------
# Telegram handlers
# -------------------------
async def start_handler(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Namaskara! Use /record to record a stream.\nFlow: /record → send stream URL → send minutes."
    )


async def record_handler(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = {"step": "ask_url"}
    await update.message.reply_text("🎥 Please send the Stream URL (m3u8/RTSP/HTTP):")


async def message_handler(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles user replies during /record flow.
    """
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()

    if user_id not in user_state:
        await update.message.reply_text("❗ Please start with /record")
        return

    step = user_state[user_id].get("step")

    if step == "ask_url":
        user_state[user_id]["stream_url"] = text
        user_state[user_id]["step"] = "ask_time"
        await update.message.reply_text("⏱️ How many minutes do you want to record? (enter integer minutes)")
        return

    if step == "ask_time":
        try:
            minutes = int(text)
            if minutes <= 0:
                raise ValueError()
        except Exception:
            await update.message.reply_text("⚠️ Please enter a valid positive integer for minutes.")
            return

        user_state[user_id]["duration_minutes"] = minutes
        stream_url = user_state[user_id]["stream_url"]
        await update.message.reply_text(f"🎬 Starting recording for {minutes} minute(s)... (stream: {stream_url})")

        # prepare output path
        timestamp = int(time.time())
        filename = f"record_{user_id}_{timestamp}.mp4"
        output_path = RECORDINGS_DIR / filename
        duration_seconds = minutes * 60

        # Run ffmpeg copy first (fast), fallback to re-encode
        try:
            code, out, err = await asyncio.to_thread(
                run_subprocess_capture, ffmpeg_cmd_copy(stream_url, str(output_path), duration_seconds)
            )
        except Exception as e:
            LOG.exception("FFmpeg copy invocation failed")
            await update.message.reply_text(f"❌ Recording failed to start: {e}")
            user_state.pop(user_id, None)
            # cleanup file if exists
            try:
                if output_path.exists():
                    output_path.unlink()
            except Exception:
                pass
            return

        if code != 0:
            LOG.warning("ffmpeg copy failed (code %s). stderr summary: %s", code, (err or "")[:400])
            # Try re-encode fallback
            await update.message.reply_text("⚠️ Copy failed; trying re-encode fallback (slower)...")
            code2, out2, err2 = await asyncio.to_thread(
                run_subprocess_capture, ffmpeg_cmd_reencode(stream_url, str(output_path), duration_seconds)
            )
            if code2 != 0:
                # both failed
                LOG.error("ffmpeg re-encode also failed. code=%s. stderr: %s", code2, (err2 or "")[:2000])
                # send trimmed stderr to user for debugging (don't overflow)
                stderr_msg = (err2 or err or "No ffmpeg stderr available").strip()
                # trim to safe length
                if len(stderr_msg) > 1500:
                    stderr_msg = stderr_msg[:1500] + "\n... (truncated)"
                await update.message.reply_text(f"❌ Recording failed. ffmpeg error:\n{stderr_msg}")
                # Save full log for further debugging
                try:
                    with open("ffmpeg_last_error.log", "w") as f:
                        f.write(err2 or err or "")
                except Exception:
                    pass
                user_state.pop(user_id, None)
                # cleanup partial file
                try:
                    if output_path.exists():
                        output_path.unlink()
                except Exception:
                    pass
                return
            else:
                LOG.info("ffmpeg re-encode succeeded.")
        else:
            LOG.info("ffmpeg copy succeeded.")

        # Upload to Telegram
        await update.message.reply_text("📤 Uploading the recorded file to Telegram (may take a while)...")
        bot = Bot(token=BOT_TOKEN)
        target_chat = DEFAULT_CHAT_ID or update.effective_chat.id
        try:
            with open(output_path, "rb") as f:
                # use send_video; this may be slow for large files
                await bot.send_video(chat_id=target_chat, video=f, caption=f"✅ Recording complete ({minutes} min)")
            await update.message.reply_text("✅ Uploaded successfully!")
        except Exception as e:
            LOG.exception("Upload failed")
            # inform user (trim)
            msg = str(e)
            if len(msg) > 1000:
                msg = msg[:1000] + "...(truncated)"
            await update.message.reply_text(f"❌ Upload failed: {msg}")
        finally:
            # cleanup local file
            try:
                if output_path.exists():
                    output_path.unlink()
            except Exception:
                pass

        # clear user state
        user_state.pop(user_id, None)


# -------------------------
# Application lifecycle
# -------------------------
def build_application():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("record", record_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    return app


async def run_bot_loop():
    """
    Runs the bot inside the current asyncio event loop.
    Handles Conflict by retrying with backoff.
    Uses initialize/start/updater.start_polling to avoid multiple event loop close issues.
    """
    global SHUTDOWN

    if not BOT_TOKEN:
        LOG.error("BOT_TOKEN not set. Exiting.")
        return

    backoff = INITIAL_BACKOFF

    while not SHUTDOWN:
        app = build_application()
        try:
            LOG.info("Initializing application...")
            await app.initialize()  # prepare internal resources
            LOG.info("Starting application...")
            await app.start()
            LOG.info("Starting polling...")
            # Start polling (this returns a coroutine for updater.start_polling)
            await app.updater.start_polling()
            LOG.info("Bot polling started; entering wait loop.")
            # keep running until shutdown requested
            while not SHUTDOWN:
                await asyncio.sleep(1)
            LOG.info("Shutdown requested; stopping bot.")
            # stop polling gracefully
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            LOG.info("Bot stopped cleanly.")
            break

        except Conflict as c:
            # Another getUpdates/poller is running for same token
            LOG.error("Conflict error from Telegram (another getUpdates running): %s", c)
            # Increase backoff and wait, then retry
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)
            # continue to retry
        except Exception as e:
            LOG.exception("Unhandled exception in bot loop; will restart after backoff")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)
        finally:
            # ensure we try to clean app resources if they are still running
            try:
                if app and app.updater:
                    # best-effort stop
                    try:
                        await app.updater.stop()
                    except Exception:
                        pass
                if app:
                    try:
                        await app.stop()
                        await app.shutdown()
                    except Exception:
                        pass
            except Exception:
                pass

    LOG.info("Exiting run_bot_loop.")


# -------------------------
# Signal handlers
# -------------------------
def _handle_signal(sig_num, frame):
    global SHUTDOWN
    LOG.info("Signal %s received, setting shutdown flag.", sig_num)
    SHUTDOWN = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# -------------------------
# Entrypoint
# -------------------------
if __name__ == "__main__":
    try:
        asyncio.run(run_bot_loop())
    except Exception:
        LOG.exception("Fatal exception in main. Exiting.")
        traceback.print_exc()
        raise
