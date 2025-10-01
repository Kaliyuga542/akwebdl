import os
import asyncio
import requests
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # optional fixed chat
NM_PATH = "N_m3u8DL-RE"   # system PATH already has /usr/local/bin
MAX_SPLIT_SIZE = 2000 * 1024 * 1024  # 2000 MB split

async def run_cmd(cmd):
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    if out:
        print(out.decode())
    if err:
        print(err.decode())
    return proc.returncode == 0

async def split_file(filepath):
    size = os.path.getsize(filepath)
    if size <= MAX_SPLIT_SIZE:
        return [filepath]

    parts = []
    base = filepath.rsplit(".", 1)[0]
    ext = filepath.rsplit(".", 1)[-1]

    part_size = MAX_SPLIT_SIZE
    i = 0
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(part_size)
            if not chunk:
                break
            part_file = f"{base}_part{i}.{ext}"
            with open(part_file, "wb") as pf:
                pf.write(chunk)
            parts.append(part_file)
            i += 1
    return parts

async def download_and_upload(url: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check for DRM key
    if "drm=" in url:
        url, key = url.split("drm=")
        cmd = [NM_PATH, url.strip(), "--save-name", "video", "--auto-select", "--binary-merge", "--key", key.strip()]
    else:
        cmd = [NM_PATH, url.strip(), "--save-name", "video", "--auto-select", "--binary-merge"]

    await update.message.reply_text(f"⚡ Running: {' '.join(cmd)}")

    success = await run_cmd(cmd)
    if not success:
        await update.message.reply_text("❌ Download failed!")
        return

    # Find file
    for f in os.listdir("."):
        if f.startswith("video"):
            filepath = f
            break

    # Split if needed
    parts = await split_file(filepath)

    for part in parts:
        await update.message.reply_document(document=open(part, "rb"))
        os.remove(part)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.startswith("http"):
        await download_and_upload(text, update, context)
    else:
        await update.message.reply_text("⚠️ Please send a valid MPD/M3U8 link.")

if __name__ == "__main__":
    print("🤖 Bot started")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.run_polling()
