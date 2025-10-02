import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import os
import subprocess

BOT_TOKEN = os.getenv("BOT_TOKEN")  # set in environment

# Run shell command async
async def run_cmd(cmd: list[str]) -> str:
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return stdout.decode() + stderr.decode()

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! Send me an m3u8/dash link and I’ll try to download it!")

# Handle messages (links)
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if url.startswith("http"):
        await update.message.reply_text(f"⚡ Running: {url}")
        cmd = ["/usr/local/bin/N_m3u8DL-RE", url, "--save-name", "video", "--auto-select", "--binary-merge"]
        output = await run_cmd(cmd)
        await update.message.reply_text(f"✅ Done!\n\nOutput:\n{output[:4000]}")
    else:
        await update.message.reply_text("❌ Not a valid URL!")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
