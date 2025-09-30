import os
import subprocess
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

# ---------------- BOT CONFIG ----------------
TELEGRAM_TOKEN = "7963130483:AAF7jKH05kIlMozC42MAlHFM98ki_YBWYjY"
DOWNLOAD_PATH = "/tmp"   # safer in servers
NM3U8DL_PATH = "/usr/local/bin/N_m3u8DL-RE"  # Path to N_m3u8DL-RE (must be installed in container)

# -------- Helper: Split large files into 2GB chunks --------
def split_file(filepath, chunk_size=2 * 1024 * 1024 * 1024):  # 2GB
    parts = []
    with open(filepath, "rb") as f:
        i = 1
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            part_name = f"{filepath}.part{i}"
            with open(part_name, "wb") as p:
                p.write(chunk)
            parts.append(part_name)
            i += 1
    return parts

# -------- Download Function --------
def download_stream(url, output_name="video"):
    output_file = os.path.join(DOWNLOAD_PATH, output_name + ".mp4")
    cmd = [
        NM3U8DL_PATH,
        url,
        "--save-name", output_name,
        "--auto-select"
    ]
    subprocess.run(cmd, check=True)
    return output_file

# -------- Telegram Handlers --------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not ("mpd" in text or "m3u8" in text):
        await update.message.reply_text("⚠️ Please send a valid MPD or M3U8 URL.")
        return

    await update.message.reply_text("⬇️ Downloading started… Please wait ⏳")

    try:
        downloaded_file = download_stream(text, "video")

        # Split if > 2GB
        file_size = os.path.getsize(downloaded_file)
        if file_size > 2 * 1024 * 1024 * 1024:
            await update.message.reply_text("📦 File >2GB, splitting into parts…")
            parts = split_file(downloaded_file)
            for idx, part in enumerate(parts, start=1):
                await update.message.reply_document(document=open(part, "rb"), caption=f"Part {idx}")
                os.remove(part)
        else:
            await update.message.reply_document(document=open(downloaded_file, "rb"))

        await update.message.reply_text("✅ Upload complete!")
        os.remove(downloaded_file)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Send me a MPD or M3U8 link and I’ll fetch the video for you 🎥")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
