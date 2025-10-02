import os
import asyncio
import glob
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters


# BOT TOKEN from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("⚠️ BOT_TOKEN not set. Please configure it as environment variable.")

# -------------------------------
# Run shell command
# -------------------------------
async def run_cmd(cmd, update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"⚡ Running: {' '.join(cmd)}")

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode == 0:
        await update.message.reply_text("✅ Download finished successfully!")
        return True, stdout.decode(), stderr.decode()
    else:
        await update.message.reply_text(f"❌ Download failed:\n{stderr.decode()}")
        return False, stdout.decode(), stderr.decode()


# -------------------------------
# Download + Upload
# -------------------------------
async def download_and_upload(url, update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_name = "video"
    cmd = [
        "/usr/local/bin/N_m3u8DL-RE",
        url,
        "--save-name", save_name,
        "--auto-select",
        "--binary-merge"
    ]

    success, stdout, stderr = await run_cmd(cmd, update, context)

    if success:
        output_files = glob.glob(f"{save_name}.*")

        if output_files:
            file_path = output_files[0]
            await update.message.reply_text("📤 Uploading file to Telegram...")

            try:
                with open(file_path, "rb") as f:
                    await update.message.reply_document(document=f)
                await update.message.reply_text("✅ Upload complete!")

                # Auto delete after upload (to save space)
                os.remove(file_path)
            except Exception as e:
                await update.message.reply_text(f"⚠️ Upload failed: {str(e)}")
        else:
            await update.message.reply_text("⚠️ No output file found after download!")


# -------------------------------
# Handlers
# -------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hi! Send me an m3u8 or mpd link and I’ll download it for you.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.startswith("http"):
        await download_and_upload(text, update, context)
    else:
        await update.message.reply_text("⚠️ Please send a valid URL.")


# -------------------------------
# Main
# -------------------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    app.run_polling()


if __name__ == "__main__":
    main()
