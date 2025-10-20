# OTT-Downloader-Bot — Deploy on Koyeb


### Environment variables
Set the following environment variables in your Koyeb app settings:


- `BOT_TOKEN` — Telegram bot token from @BotFather
- `API_ID` — Telegram API ID from my.telegram.org
- `API_HASH` — Telegram API HASH from my.telegram.org
- `OWNER_ID` — (optional) your Telegram user id for admin commands
- `MAX_FILE_SIZE_MB` — (optional) maximum file size the bot will send (default 45)


### Steps
1. Create a new Koyeb app (select Python image)
2. Push this repo to GitHub and connect the repo to Koyeb, or upload the files directly.
3. Set the environment variables above in the Koyeb dashboard.
4. Start the app (Koyeb should run `python main.py` as per `Procfile`).


### Notes & next steps
- This bot uses `yt-dlp` to download videos. For DRM-protected content, `yt-dlp` will either fail or return no downloadable formats — the bot reports that back.
- You said you'll add DRM keys later — when you have them, we can add a plugin layer to pass those keys to a custom extractor.
- For large files (> MAX_FILE_SIZE_MB) the bot currently aborts. You can integrate external hosting (S3, Wasabi, etc.) for large file uploads.
