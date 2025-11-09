#!/usr/bin/env python3
"""
Telegram Live Stream Recorder Bot (MPD/m3u8) with HEADERS parsing.

- Exposes /health endpoint via aiohttp (for Koyeb health checks / UptimeRobot)
- /record flow: user sends URL and optional HEADERS: block (see README)
- FFmpeg: tries -c copy first, falls back to re-encode
- HEADERS block syntax:
    HEADERS:
    Referer: https://example.com
    User-Agent: Mozilla/5.0 ...
    Cookie: session=abcd1234
  (Bot will join lines with \r\n and pass to ffmpeg via -headers)
"""

import os
import asyncio
import logging
import signal
import shlex
import subprocess
import time
import traceback
from pathlib import Path

from aiohttp import web
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
# Configuration
# -------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEFAULT_CHAT_ID = os.getenv("CHAT_ID")
PORT = int(os.getenv("PORT", "8000"))
RECORDINGS_DIR = Path("recordings")
RECORDINGS_DIR.mkdir(exist_ok=True)

INITIAL_BACKOFF = 5
MAX_BACKOFF = 120

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("recorder-bot")

# State
SHUTDOWN = False
user_state = {}  # {user_id: {"step": ..., "stream_url": ..., "duration_minutes": ...}}

# -------------------------
# Utilities: parse HEADERS block
# -------------------------
def extract_url_and_headers(text: str):
    """
    Parse a message that may contain a URL on first line and an optional HEADERS: block.
    Returns (url, headers_str_or_None)
    """
    if not text:
        return None, None
    parts = text.splitlines()
    url = None
    headers_lines = []
    in_headers = False
    for raw in parts:
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("HEADERS:"):
            # begin headers block
            in_headers = True
            remainder = line[len("HEADERS:"):].strip()
            if remainder:
                headers_lines.append(remainder)
            continue
        if in_headers:
            headers_lines.append(line)
        elif url is None:
            url = line
        else:
            # extra lines before headers ignored
            pass

    headers_str = None
    if headers_lines:
        # join with \r\n and ensure trailing \r\n (ffmpeg expects CRLF line endings)
        headers_str = "\r\n".join(headers_lines).strip() + "\r\n"
    return url, headers_str

# -------------------------
# FFmpeg helpers (MPD/DASH aware)
# -------------------------
def ffmpeg_cmd_copy(stream_url: str, output_path: str, duration_seconds: int, headers: str = None):
    """
    Construct ffmpeg command for direct copy (fast).
    If headers provided, insert '-headers' before '-i'.
    """
    if headers:
        cmd = [
            "ffmpeg",
            "-headers",
            headers,
            "-protocol_whitelist",
            "file,http,https,tcp,tls",
            "-rw_timeout",
            str(15_000_000),
            "-y",
            "-use_wallclock_as_timestamps",
            "1",
            "-i",
            stream_url,
            "-t",
            str(duration_seconds),
            "-c",
            "copy",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg",
            "-protocol_whitelist",
            "file,http,https,tcp,tls",
            "-rw_timeout",
            str(15_000_000),
            "-y",
            "-use_wallclock_as_timestamps",
            "1",
            "-i",
            stream_url,
            "-t",
            str(duration_seconds),
            "-c",
            "copy",
            output_path,
        ]
    return cmd

def ffmpeg_cmd_reencode(stream_url: str, output_path: str, duration_seconds: int, headers: str = None):
    """
    Construct ffmpeg command for re-encode fallback.
    """
    if headers:
        cmd = [
            "ffmpeg",
            "-headers",
            headers,
            "-protocol_whitelist",
            "file,http,https,tcp,tls",
            "-rw_timeout",
            str(15_000_000),
            "-y",
            "-use_wallclock_as_timestamps",
            "1",
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
    else:
        cmd = [
            "ffmpeg",
            "-protocol_whitelist",
            "file,http,https,tcp,tls",
            "-rw_timeout",
            str(15_000_000),
            "-y",
            "-use_wallclock_as_timestamps",
            "1",
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
    return cmd

def run_subprocess_capture(cmd):
    """Run blocking subprocess and capture output."""
    LOG.info("Running command: %s", shlex.join(cmd))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.returncode, proc.stdout, proc.stderr

# -------------------------
# Telegram handlers
# -------------------------
async def start_handler(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Namaskara! Use /record to record a stream.\nFlow: /record -> send URL (and optional HEADERS: block) -> send minutes."
    )

async def record_handler(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = {"step": "ask_url"}
    await update.message.reply_text(
        "🎥 Please send the Stream URL (mpd/m3u8/RTSP/HTTP). If the stream requires headers/cookies, append a HEADERS: block.\n\nExample:\n<url>\n\nHEADERS:\nReferer: https://example.com\nUser-Agent: Mozilla/5.0\nCookie: session=abcd"
    )

async def message_handler(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()

    if user_id not in user_state:
        await update.message.reply_text("❗ Please start with /record")
        return

    step = user_state[user_id].get("step")

    # Step: receive URL (and optional headers block) in one message
    if step == "ask_url":
        url, headers_block = extract_url_and_headers(text)
        if not url:
            await update.message.reply_text("⚠️ Could not parse URL. Please send the stream URL on the first non-empty line.")
            return
        user_state[user_id]["stream_url"] = url
        user_state[user_id]["headers_block"] = headers_block
        user_state[user_id]["step"] = "ask_time"
        await update.message.reply_text("⏱️ How many minutes do you want to record? (enter integer minutes)")
        return

    # Step: receive duration
    if step == "ask_time":
        try:
            minutes = int(text)
            if minutes <= 0:
                raise ValueError()
        except Exception:
            await update.message.reply_text("⚠️ Please enter a valid positive integer for minutes.")
            return

        stream_url = user_state[user_id].get("stream_url")
        headers_block = user_state[user_id].get("headers_block")
        user_state[user_id]["duration_minutes"] = minutes

        await update.message.reply_text(f"🎬 Recording started for {minutes} minute(s). Stream: {stream_url}")

        # Prepare output path
        ts = int(time.time())
        filename = f"record_{user_id}_{ts}.mp4"
        output_path = RECORDINGS_DIR / filename
        duration_seconds = minutes * 60

        # Run ffmpeg copy -> re-encode fallback
        try:
            code, out, err = await asyncio.to_thread(
                run_subprocess_capture, ffmpeg_cmd_copy(stream_url, str(output_path), duration_seconds, headers=headers_block)
            )
        except Exception as e:
            LOG.exception("Failed to invoke ffmpeg copy")
            await update.message.reply_text(f"❌ Recording failed to start: {e}")
            user_state.pop(user_id, None)
            try:
                if output_path.exists():
                    output_path.unlink()
            except Exception:
                pass
            return

        if code != 0:
            LOG.warning("ffmpeg copy failed (code %s). stderr head: %s", code, (err or "")[:400])
            await update.message.reply_text("⚠️ Fast copy failed; trying re-encode fallback (slower)...")
            try:
                code2, out2, err2 = await asyncio.to_thread(
                    run_subprocess_capture, ffmpeg_cmd_reencode(stream_url, str(output_path), duration_seconds, headers=headers_block)
                )
            except Exception as e:
                LOG.exception("Failed to invoke ffmpeg re-encode")
                await update.message.reply_text(f"❌ Recording failed: {e}")
                user_state.pop(user_id, None)
                try:
                    if output_path.exists():
                        output_path.unlink()
                except Exception:
                    pass
                return

            if code2 != 0:
                LOG.error("ffmpeg re-encode failed code=%s. stderr head: %s", code2, (err2 or "")[:2000])
                stderr_msg = (err2 or err or "No ffmpeg stderr available").strip()
                if len(stderr_msg) > 1400:
                    stderr_msg = stderr_msg[:1400] + "\n...(truncated)"
                await update.message.reply_text(f"❌ Recording failed. ffmpeg error:\n{stderr_msg}")
                try:
                    with open("ffmpeg_last_error.log", "w") as f:
                        f.write(err2 or err or "")
                except Exception:
                    pass
                user_state.pop(user_id, None)
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

        # Upload
        await update.message.reply_text("📤 Uploading recorded file to Telegram (may take a while)...")
        bot = Bot(token=BOT_TOKEN)
        target_chat = DEFAULT_CHAT_ID or update.effective_chat.id
        try:
            with open(output_path, "rb") as f:
                await bot.send_video(chat_id=target_chat, video=f, caption=f"✅ Recording complete ({minutes} min)")
            await update.message.reply_text("✅ Uploaded successfully!")
        except Exception as e:
            LOG.exception("Upload failed")
            msg = str(e)
            if len(msg) > 1000:
                msg = msg[:1000] + "...(truncated)"
            await update.message.reply_text(f"❌ Upload failed: {msg}")
        finally:
            try:
                if output_path.exists():
                    output_path.unlink()
            except Exception:
                pass

        user_state.pop(user_id, None)
        return

# -------------------------
# Build application and health server
# -------------------------
def build_application():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("record", record_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    return app

# aiohttp health endpoint
async def health_handler(request):
    return web.Response(text="ok")

async def start_health_server():
    app = web.Application()
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    LOG.info("Health server listening on 0.0.0.0:%s", PORT)

# -------------------------
# Bot run loop (async)
# -------------------------
async def run_bot_loop():
    global SHUTDOWN
    if not BOT_TOKEN:
        LOG.error("BOT_TOKEN not set. Exiting.")
        return

    # start health server so Koyeb sees the app as healthy
    await start_health_server()

    backoff = INITIAL_BACKOFF
    while not SHUTDOWN:
        app = build_application()
        try:
            LOG.info("Initializing application...")
            await app.initialize()
            LOG.info("Starting application...")
            await app.start()
            LOG.info("Starting polling...")
            await app.updater.start_polling()
            LOG.info("Bot polling started; entering wait loop.")
            # main wait loop
            while not SHUTDOWN:
                await asyncio.sleep(1)
            LOG.info("Shutdown requested; stopping bot.")
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            break
        except Conflict as c:
            LOG.error("Conflict error (another getUpdates running): %s", c)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)
        except Exception as e:
            LOG.exception("Unhandled exception in bot loop; will restart after backoff")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)
        finally:
            # best-effort cleanup
            try:
                if app and app.updater:
                    await app.updater.stop()
            except Exception:
                pass
            try:
                await app.stop()
                await app.shutdown()
            except Exception:
                pass

    LOG.info("Exiting run_bot_loop.")

# -------------------------
# Signals
# -------------------------
def _sig_handler(sig_num, frame):
    global SHUTDOWN
    LOG.info("Signal %s received; setting shutdown flag.", sig_num)
    SHUTDOWN = True

signal.signal(signal.SIGTERM, _sig_handler)
signal.signal(signal.SIGINT, _sig_handler)

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
