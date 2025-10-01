import os
import asyncio
import subprocess
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ----------- Helper: run command async -----------
async def run_cmd(cmd):
    print("⚡ Running:", " ".join(cmd), flush=True)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        print("❌ Error:", stderr.decode())
        return False
    print("✅ Done")
    return True

# ----------- Split and upload -----------
async def split_and_upload(file_path, update: Update, context: ContextTypes.DEFAULT_TYPE):
    max_size = 2000 * 1024 * 1024  # 2000MB ~ 2GB
    size = os.path.getsize(file_path)

    if size <= max_size:
        await update.message.reply_document(document=open(file_path, "rb"))
        return

    # Split file >2GB
    part_num = 1
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(max_size)
            if not chunk:
                break
            part_name = f"{file_path}.part{part_num}"
            with open(part_name, "wb") as p:
                p.write(chunk)
            await update.message.reply_document(document=open(part_name, "rb"))
            os.remove(part_name)
            part_num += 1

# ----------- Main Download Logic -----------
async def download_and_upload(url, update: Update, context: ContextTypes.DEFAULT_TYPE):
    # If DRM protected → ask for key
    if "drm" in url.lower():
        await update.message.reply_text("🔑 DRM protected stream detected. Please provide decryption key.")
        return

    out_file = "video.mp4"

    # Try N_m3u8DL-RE first
    cmd = ["N_m3u8DL-RE", url, "--save-name", "video", "--auto-select", "--binary-merge"]
    success = await run_cmd(cmd)

    if not success or not os.path.exists(out_file):
        # fallback to ffmpeg
        cmd = ["ffmpeg", "-y", "-i", url, "-c", "copy", out_file]
        success = await run_cmd(cmd)

    if success and os.path.exists(out_file):
        await split_and_upload(out_file, update, context)
        os.remove(out_file)
    else:
        await update.message.reply_text("❌ Download failed. Check logs.")

# ----------- Handler -----------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.startswith("http"):
        await update.message.reply_text("⏳ Processing link...")
        await download_and_upload(text, update, context)
    else:
        await update.message.reply_text("Send me a mpd/m3u8/video link.")

# ----------- Run Bot -----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("🤖 Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
