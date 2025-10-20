# main.py (recommended replacement)
import os
import tempfile
import asyncio
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import Message
from yt_dlp import YoutubeDL
from config import BOT_TOKEN, API_ID, API_HASH, OWNER_ID, MAX_FILE_SIZE_MB

app = Client("ott_bot",
             bot_token=BOT_TOKEN,
             api_id=int(API_ID),
             api_hash=API_HASH)

ALLOWED_DOMAINS = [
    "hotstar.com", "disneyplus.com", "zee5.com", "sonyliv.com",
    "mxplayer.in", "voot.com", "youtube.com", "youtu.be"
]

URL_PREFIX = ("http://", "https://")
MAX_BYTES = int(MAX_FILE_SIZE_MB) * 1024 * 1024

def is_allowed_url(url: str) -> bool:
    return any(domain in url for domain in ALLOWED_DOMAINS)

def yt_download_blocking(url: str, out_dir: str) -> str:
    opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": str(Path(out_dir) / "%(title).200s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = info.get("formats") or []
        if not formats:
            raise RuntimeError("No downloadable formats (possible DRM)")
        ydl.download([url])
    files = list(Path(out_dir).glob("*"))
    if not files:
        raise RuntimeError("Downloaded but file not found")
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return str(latest)

@app.on_message(filters.private & filters.command(["start", "help"]))
async def start(_, message: Message):
    await message.reply_text(
        "Send a direct OTT/video URL (free/non-DRM). I try to download and send the file. I cannot bypass DRM."
    )

@app.on_message(filters.private & filters.text)
async def handle(_, message: Message):
    text = message.text.strip()
    # find URL simply
    url = None
    for token in text.split():
        if token.startswith(URL_PREFIX):
            url = token
            break
    if not url:
        return await message.reply_text("Please send a direct URL.")

    if not is_allowed_url(url):
        return await message.reply_text("Domain not allowed. Add to ALLOWED_DOMAINS if needed.")

    progress = await message.reply_text("Starting download... (this may take a while)")
    with tempfile.TemporaryDirectory() as tmp:
        loop = asyncio.get_event_loop()
        try:
            # Run blocking downloader in executor
            filepath = await loop.run_in_executor(None, yt_download_blocking, url, tmp)
        except Exception as e:
            await progress.edit_text(f"Download failed: {e}")
            return

        try:
            size = Path(filepath).stat().st_size
            if size > MAX_BYTES:
                await progress.edit_text(
                    f"File too large ({size//1024//1024} MB). Max is {MAX_FILE_SIZE_MB} MB. "
                    "Consider external upload."
                )
                return

            await progress.edit_text("Uploading to Telegram...")
            await app.send_document(message.chat.id, document=filepath, caption=f"From: {url}")
            await progress.delete()
        except Exception as e:
            await progress.edit_text(f"Failed to send file: {e}")

async def main():
    await asyncio.sleep(2)  # give time for container clock to sync
    await app.start()
    print("Bot started successfully ✅")
    await idle()
    await app.stop()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
