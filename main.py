import os
import subprocess
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

# Telegram Bot Token from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Save files inside container
DOWNLOAD_PATH = "/app/downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

# Path to N_m3u8DL-RE (installed in Dockerfile)
NM3U8DL_PATH = "/usr/local/bin/N_m3u8DL-RE"

def download_mpd(mpd_url, output_name="video"):
    output_file = os.path.join(DOWNLOAD_PATH, output_name + ".mp4")
    cmd = [
        NM3U8DL_PATH,
        mpd_url,
        "--save-name", output_name,
        "--auto-select",
        "--binary-merge"
    ]
    subprocess.run(cmd, check=True)
    return output_file


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.endswith(".mpd"):
        await update.message.reply_text("❌ Please send a valid MPD link.")
        return

    await update.message.reply_text("⏬ Downloading, please wait...")
    output_name = "video"

    try:
        downloaded_file = download_mpd(text, output_name)
        await update.message.reply_document(document=open(downloaded_file, "rb"))
        await update.message.reply_text("✅ Upload complete!")
        os.remove(downloaded_file)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Send me a DASH/MPD link and I’ll download + upload.")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
