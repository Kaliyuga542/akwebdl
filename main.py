#!/usr/bin/env python3
"""
main.py - Telegram bot to analyze MPD/m3u8, let user choose quality,
download with N_m3u8DL-RE, support partial (hh:mm:ss) downloads,
and upload to Telegram (auto-split >2GB).

IMPORTANT: This script DOES NOT help bypass DRM. If you have a legal
decryption key, you may set the DECRYPTION_KEY env var. Do NOT use this
to obtain keys illegally.
"""

import os
import json
import shutil
import tempfile
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from functools import partial
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------- Configuration (prefer env vars) ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "7963130483:AAF7jKH05kIlMozC42MAlHFM98ki_YBWYjY")
NM3U8DL_PATH = os.getenv("NM3U8DL_PATH", "/usr/local/bin/N_m3u8DL-RE")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp")
DECRYPTION_KEY = os.getenv("DECRYPTION_KEY", None)  # Optional: ONLY use if you own it

# Telegram per-file limit (regular bots): 2GB
TG_MAX_BYTES = 2 * 1024 * 1024 * 1024

# In-memory session store (simple)
SESSIONS = {}  # user_id -> dict with session state

# ---------- Helpers ----------
def run_health_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
    server = HTTPServer(("0.0.0.0", 8000), Handler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()
    
def run_cmd_sync(cmd, cwd=None, env=None, timeout=None):
    """Run blocking subprocess in synchronous context (used via executor)."""
    import subprocess
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=env, timeout=timeout)
    return proc

def nm_info_json(link):
    """Run N_m3u8DL-RE --get-info-json and return parsed JSON (or None)."""
    cmd = [NM3U8DL_PATH, link, "--get-info-json"]
    if DECRYPTION_KEY:
        # If user has provided a legit key, append as an option — this assumes N_m3u8DL-RE supports something like --key (adjust if needed)
        # NOTE: DO NOT use this to bypass DRM. Only if you legally have the key.
        cmd += ["--key", DECRYPTION_KEY]
    proc = run_cmd_sync(cmd)
    if proc.returncode != 0:
        return None, proc.stderr
    try:
        info = json.loads(proc.stdout)
        return info, None
    except Exception as e:
        return None, f"JSON parse error: {e}"

def build_quality_buttons(info):
    """Build list of (video, audio) tuples based on info JSON."""
    video_list = info.get("video", [])
    audio_list = info.get("audio", [])
    # Prepare buttons: show resolution/bitrate + audio codec
    rows = []
    for v in video_list:
        vlabel = v.get("resolution") or str(v.get("bitrate") or "")
        for a in audio_list:
            alabel = a.get("codec") or str(a.get("bitrate") or "")
            rows.append([InlineKeyboardButton(f"{vlabel} / {alabel}", callback_data=f"Q|{vlabel}|{alabel}")])
    return InlineKeyboardMarkup(rows)

def parse_hms_to_seconds(hms: str):
    parts = hms.strip().split(":")
    if len(parts) != 3:
        raise ValueError("Format should be hh:mm:ss")
    h, m, s = map(int, parts)
    return h * 3600 + m * 60 + s

def split_file_if_needed(path: Path):
    """If file > TG_MAX_BYTES, split it into parts in same directory and return list of paths."""
    size = path.stat().st_size
    if size <= TG_MAX_BYTES:
        return [path]
    parts = []
    chunk = TG_MAX_BYTES
    idx = 1
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            part_path = path.with_suffix(path.suffix + f".part{idx}")
            with open(part_path, "wb") as p:
                p.write(data)
            parts.append(part_path)
            idx += 1
    # remove original big file after splitting to free disk
    try:
        path.unlink()
    except Exception:
        pass
    return parts

def build_nmd_cmd(link, output_name, video_sel=None, audio_sel=None, duration_seconds=None):
    """
    Build N_m3u8DL-RE command.
    Note: Adjust arguments if your N_m3u8DL-RE uses different flags for stream selection.
    """
    cmd = [NM3U8DL_PATH, link, "--save-name", output_name, "--auto-select"]
    # If a decryption key is provided externally and supported, attach it (only if you have legal rights)
    if DECRYPTION_KEY:
        cmd += ["--key", DECRYPTION_KEY]
    if duration_seconds:
        cmd += ["--download-seconds", str(duration_seconds)]
    # --video-bitrate / --audio-bitrate placeholders: N_m3u8DL-RE accepts track selection options which depend on version
    # We include them only if user provided simple labels (the real tool may require different flags). Keep as-is or adapt.
    if video_sel:
        cmd += ["--video-bitrate", str(video_sel)]
    if audio_sel:
        cmd += ["--audio-bitrate", str(audio_sel)]
    return cmd

# ---------- Telegram handlers ----------

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send an MPD or M3U8 URL and I'll analyze available qualities. (I cannot download DRM-protected content without legal keys.)")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Please send a text MPD or M3U8 URL.")
        return

    # If we're waiting for duration input
    sess = SESSIONS.get(user_id)
    if sess and sess.get("awaiting_duration"):
        # Expect hh:mm:ss or 'full'
        if text.lower() == "full":
            duration_seconds = None
        else:
            try:
                duration_seconds = parse_hms_to_seconds(text)
            except Exception:
                await update.message.reply_text("Invalid format. Send duration as hh:mm:ss (e.g., 00:05:30) or 'full'.")
                return
        sess["duration_seconds"] = duration_seconds
        sess["awaiting_duration"] = False
        # Kick off download in background
        await update.message.reply_text("Starting download (this may take a while)…")
        asyncio.create_task(do_download_and_upload(update, context, user_id))
        return

    # New incoming link - validate
    if not ("mpd" in text.lower() or "m3u8" in text.lower() or text.startswith("http")):
        await update.message.reply_text("Please send a valid MPD or M3U8 URL (http/https...).")
        return

    # Analyze link for qualities (this is blocking; run in executor)
    await update.message.reply_text("Analyzing manifest for available qualities…")
    loop = asyncio.get_running_loop()
    info, err = await loop.run_in_executor(None, partial(nm_info_json, text))
    if not info:
        await update.message.reply_text(f"Failed to analyze link. Error: {err or 'unknown'}")
        return

    # Save session
    SESSIONS[user_id] = {"link": text, "info": info}

    # Build and send quality buttons
    kb = build_quality_buttons(info)
    if not kb.inline_keyboard:
        await update.message.reply_text("No qualities found in manifest.")
        return
    await update.message.reply_text("Select video/audio quality:", reply_markup=kb)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    payload = query.data
    if not payload:
        await query.edit_message_text("Invalid selection.")
        return
    parts = payload.split("|")
    if parts[0] != "Q" or len(parts) < 3:
        await query.edit_message_text("Invalid quality payload.")
        return

    video_sel = parts[1]
    audio_sel = parts[2]
    sess = SESSIONS.get(user_id)
    if not sess:
        await query.edit_message_text("Session expired. Send link again.")
        return

    sess["video_sel"] = video_sel
    sess["audio_sel"] = audio_sel
    sess["awaiting_duration"] = True
    # ask for duration
    await query.edit_message_text("Choose download mode:\n- Send duration in hh:mm:ss (e.g., 00:05:00)\n- Or send 'full' to download full video")

async def do_download_and_upload(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """
    Perform the N_m3u8DL-RE download (in background), split if needed and upload to Telegram.
    This function runs asynchronously but offloads blocking subprocess calls to an executor.
    """
    sess = SESSIONS.get(user_id)
    if not sess:
        return
    link = sess.get("link")
    video_sel = sess.get("video_sel")
    audio_sel = sess.get("audio_sel")
    duration_seconds = sess.get("duration_seconds")

    # Prepare safe output dir
    tmpdir = Path(tempfile.mkdtemp(prefix="bot_dl_"))
    output_name = "video"  # base
    output_file = tmpdir / f"{output_name}.mp4"

    cmd = build_nmd_cmd(link, output_name, video_sel=video_sel, audio_sel=audio_sel, duration_seconds=duration_seconds)
    # Run blocking download in executor
    loop = asyncio.get_running_loop()
    await context.bot.send_message(chat_id=user_id, text=f"Downloading using: {' '.join(cmd[:6])} ...")
    try:
        proc = await loop.run_in_executor(None, partial(run_cmd_sync, cmd, tmpdir))
        if proc.returncode != 0:
            err = proc.stderr or "Unknown error"
            await context.bot.send_message(chat_id=user_id, text=f"Download failed: {err[:1000]}")
            shutil.rmtree(tmpdir, ignore_errors=True)
            SESSIONS.pop(user_id, None)
            return

        if not output_file.exists():
            # N_m3u8DL-RE may save with another name; attempt to find largest file in tmpdir
            files = list(tmpdir.glob("*"))
            if not files:
                await context.bot.send_message(chat_id=user_id, text="Download finished but no output file found.")
                shutil.rmtree(tmpdir, ignore_errors=True)
                SESSIONS.pop(user_id, None)
                return
            # pick largest file
            output_file = max(files, key=lambda p: p.stat().st_size)

        # Now split if needed
        parts = split_file_if_needed(output_file)
        # Upload each part
        for idx, part in enumerate(parts, start=1):
            caption = f"Part {idx}/{len(parts)}" if len(parts) > 1 else None
            await context.bot.send_message(chat_id=user_id, text=f"Uploading {part.name} ({part.stat().st_size // (1024*1024)} MB)...")
            # Use InputFile; open in binary
            with open(part, "rb") as fh:
                # send_document is async; keep it awaited
                await context.bot.send_document(chat_id=user_id, document=InputFile(fh, filename=part.name), caption=caption)
            # Remove part after upload to free space
            try:
                Path(part).unlink()
            except Exception:
                pass

        await context.bot.send_message(chat_id=user_id, text="All done ✅")
    except Exception as e:
        await context.bot.send_message(chat_id=user_id, text=f"Unexpected error: {e}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        SESSIONS.pop(user_id, None)

# ---------- Main ----------
def main():
    if not shutil.which(NM3U8DL_PATH):
        print(f"Warning: N_m3u8DL-RE not found at {NM3U8DL_PATH}. Ensure the binary is installed and path is correct.")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Bot started.")
    app.run_polling()

if __name__ == "__main__":
    main()
