# main.py
import os
import subprocess
import asyncio
import requests
import logging
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    ContextTypes,
    CommandHandler,
)

# ---------- CONFIG ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set.")

CHUNK_SIZE = 1900 * 1024 * 1024  # 1.9 GB chunks
TEMP_DIR = "./tmp_stream"
os.makedirs(TEMP_DIR, exist_ok=True)

# simple in-memory user state (non-persistent)
user_state = {}  # {chat_id: {"expecting": "license_confirm", "url": "..."}}

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------- DRM detection helpers ----------
def fetch_head(url: str, max_bytes: int = 4096) -> str:
    """Fetch a small portion (or full manifest if small) for inspection."""
    try:
        # Try Range header to get small portion without fetching entire media
        headers = {"Range": f"bytes=0-{max_bytes}"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code in (200, 206):
            return resp.text.lower()
        # fallback to full GET if Range not supported
        resp = requests.get(url, timeout=10)
        return resp.text.lower() if resp.status_code == 200 else ""
    except Exception as e:
        logger.warning("fetch_head error for %s: %s", url, str(e))
        return ""


def is_drm_manifest(url: str) -> bool:
    """Heuristic checks for DRM indicators in mpd or m3u8 manifests."""
    content = fetch_head(url)
    if not content:
        return False

    # MPD/DASH DRM clues
    if "cenc:default_kid" in content or "pssh" in content or "protection" in content or "widevine" in content:
        return True

    # HLS DRM clues
    if "#ext-x-key" in content or "sample-aes" in content or "encryption" in content:
        return True

    return False


# ---------- streaming + chunking helpers ----------
async def stream_and_upload_parts(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    bot = context.bot  # <-- v20+ correct way
    """
    Stream the manifest via ffmpeg and upload in CHUNK_SIZE parts.
    Uses run_in_executor for blocking IO to avoid blocking the event loop.
    """
    chat_id = update.effective_chat.id
    bot = update.message.bot
    await update.message.reply_text("📥 Streaming download started (pipe → chunked upload)...")

    # ffmpeg command: input manifest, copy streams to MP4 container, pipe to stdout
    cmd = ["ffmpeg", "-y", "-i", url, "-c", "copy", "-f", "mp4", "pipe:1"]

    # start ffmpeg subprocess
    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10 ** 8
        )
    except FileNotFoundError:
        await update.message.reply_text("❌ ffmpeg not found in container. Please install ffmpeg.")
        return
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to start ffmpeg: {str(e)}")
        return

    loop = asyncio.get_running_loop()
    part = 1

    try:
        while True:
            # read a chunk from ffmpeg stdout in a thread to avoid blocking
            chunk = await loop.run_in_executor(None, process.stdout.read, CHUNK_SIZE)
            if not chunk:
                break

            tmp_name = os.path.join(TEMP_DIR, f"part_{chat_id}_{part}.mp4")

            # write chunk to temp file in thread
            await loop.run_in_executor(None, _write_bytes_to_file, tmp_name, chunk)

            # notify and upload
            await update.message.reply_text(f"⬆️ Uploading part {part} ...")
            try:
                # upload as document (safer for large files)
                with open(tmp_name, "rb") as fp:
                    await bot.send_document(chat_id=chat_id, document=fp, filename=os.path.basename(tmp_name))
            except Exception as e:
                await update.message.reply_text(f"❌ Upload failed for part {part}: {str(e)}")
                # continue cleanup and try next or abort
                logger.exception("Upload failed")
                # Best effort: remove file then break
                await loop.run_in_executor(None, _safe_remove, tmp_name)
                break

            # cleanup part after upload
            await loop.run_in_executor(None, _safe_remove, tmp_name)
            part += 1

        # wait for ffmpeg to finish
        await loop.run_in_executor(None, process.stdout.close)
        await loop.run_in_executor(None, process.stderr.close)
        await loop.run_in_executor(None, process.wait)
        await update.message.reply_text("✅ All parts uploaded successfully.")
    except Exception as e:
        logger.exception("stream_and_upload_parts error")
        try:
            process.kill()
        except Exception:
            pass
        await update.message.reply_text(f"❌ Streaming/upload error: {str(e)}")


def _write_bytes_to_file(path: str, data: bytes):
    """Blocking helper to write bytes to a file."""
    with open(path, "wb") as f:
        f.write(data)


def _safe_remove(path: str):
    """Blocking helper to remove a file quietly."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        logger.exception("Failed to remove %s", path)


# ---------- Handlers ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! Send an mpd or m3u8 link and I'll attempt a streaming download and chunked upload (non-DRM only)."
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    # check if user was asked about license possession
    state = user_state.get(chat_id, {})
    expecting = state.get("expecting")

    # If expecting confirmation about license/keys after DRM detection
    if expecting == "license_confirm":
        lower = text.lower()
        if lower in ("yes", "y", "ha", "ಹೌದು"):
            # user claims to have license/keys — we refuse to decrypt but offer guidance
            await update.message.reply_text(
                "ನೋಟ್: ನಾನು DRM decrypt/keys ಬಳಸಿ content download ಮಾಡಲು ಸಹಾಯ ಮಾಡಲ್ಲ.\n\n"
                "ನಿಮ್ಮಲ್ಲಿ license server / keys ಇದ್ದರೆ, authorized playback (ExoPlayer/Shaka) integration ಮತ್ತು server-side license-request flow ನಲ್ಲಿ ಸಹಾಯ ಮಾಡಬಹುದು.\n"
                "ಅಥವಾ content owner/ distributor ನಿಂದ authorized export/API ಕೇಳಿ.\n\n"
                "ನೀವು authorization integration ಕುರಿತು உதவி ಕೇಳಿದರೆ ನಾನು high-level code samples ಕೊಡುತ್ತೇನೆ."
            )
            user_state.pop(chat_id, None)
            return
        else:
            # user said NO — proceed with non-DRM streaming attempt
            url = state.get("url")
            user_state.pop(chat_id, None)
            if not url:
                await update.message.reply_text("Bad state: URL missing. Please resend the link.")
                return
            await update.message.reply_text("Proceeding with non-DRM streaming download...")
            await stream_and_upload_parts(update, url)
            return

    # Normal incoming text -> detect links
    if text.endswith(".mpd") or text.endswith(".m3u8") or "m3u8" in text or "mpd" in text:
        url = text
        await update.message.reply_text("🔎 Inspecting manifest for DRM indicators...")
        try:
            drm = is_drm_manifest(url)
        except Exception as e:
            logger.exception("DRM detection error")
            drm = False

        if drm:
            # Ask user if they legally have keys/license (we still won't decrypt)
            user_state[chat_id] = {"expecting": "license_confirm", "url": url}
            await update.message.reply_text(
                "⚠️ This stream appears to be DRM-protected.\n"
                "Do you have a legal license/key for this content? Reply YES if you do (note: I WILL NOT use keys to decrypt),\n"
                "or reply NO to attempt non-DRM download (if possible)."
            )
            return
        else:
            # Not DRM -> proceed streaming+upload
            await update.message.reply_text("No DRM detected — starting streaming download/upload...")
            await stream_and_upload_parts(update, url)
            return

    # fallback
    await update.message.reply_text("Send an mpd or m3u8 link (plain URL).")


# ---------- Main ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Run polling (if you deploy with webhook, change accordingly)
    app.run_polling()


if __name__ == "__main__":
    main()
