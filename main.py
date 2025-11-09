import os
import subprocess
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Temporary user state
user_state = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Namaskara! Type /record to start recording a stream.")

async def record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = {"step": "ask_url"}
    await update.message.reply_text("🎥 Please send the Stream URL (m3u8/RTSP):")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in user_state:
        await update.message.reply_text("❗ Please type /record first.")
        return

    step = user_state[user_id]["step"]

    # Step 1: Get URL
    if step == "ask_url":
        user_state[user_id]["stream_url"] = text
        user_state[user_id]["step"] = "ask_time"
        await update.message.reply_text("⏱️ How many minutes do you want to record?")
        return

    # Step 2: Get time
    if step == "ask_time":
        try:
            minutes = int(text)
        except ValueError:
            await update.message.reply_text("⚠️ Please enter a valid number of minutes.")
            return

        user_state[user_id]["duration"] = minutes
        stream_url = user_state[user_id]["stream_url"]

        await update.message.reply_text(f"🎬 Recording started for {minutes} minutes...")
        output_file = f"record_{user_id}.mp4"

        # Run FFmpeg command
        subprocess.run([
            "ffmpeg", "-y", "-i", stream_url, "-t", str(minutes * 60),
            "-c", "copy", output_file
        ])

        # Upload video to Telegram
        await update.message.reply_text("📤 Uploading to Telegram, please wait...")
        from telegram import Bot
        bot = Bot(token=BOT_TOKEN)
        await bot.send_video(chat_id=CHAT_ID or user_id, video=open(output_file, "rb"),
                             caption=f"✅ Recording complete ({minutes} min)")

        os.remove(output_file)
        del user_state[user_id]
        await update.message.reply_text("✅ Done! You can type /record again if you want another.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("record", record))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
