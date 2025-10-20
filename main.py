# main.py
)
elif d.get('status') == 'finished':
asyncio.get_event_loop().create_task(
progress_msg.edit_text("Download finished, preparing to send...")
)
except Exception:
pass


ytdl_opts['progress_hooks'] = [progress_hook]
ytdl_opts['outtmpl'] = str(Path(download_dir) / "%(title).200s.%(ext)s")


with YoutubeDL(ytdl_opts) as ytdl:
info = ytdl.extract_info(url, download=False)


# quick DRM-ish detection: if extractor or formats indicate encrypted/protected, abort
# This is heuristic; yt-dlp may raise ExtractorError for truly unsupported/DRM content
formats = info.get('formats') or []
if not formats:
raise RuntimeError("No downloadable formats detected (possible DRM or protected stream)")


# start actual download
result = ytdl.download([url])


# find downloaded file in download_dir (most recent)
files = list(Path(download_dir).glob('*'))
if not files:
raise RuntimeError("Download completed but file not found")


latest = max(files, key=lambda p: p.stat().st_mtime)
return str(latest)




@app.on_message(filters.private & filters.command(['start', 'help']))
async def start_cmd(client, message: Message):
await message.reply_text(
"Hello! Send me an OTT link (free/non-DRM). I will try to download and send the video.\n\n" \
"⚠️ I cannot bypass DRM-protected content. If the link is DRM-protected the bot will report an error."
)




@app.on_message(filters.private & filters.text)
async def handle_text(client, message: Message):
text = message.text.strip()
urls = URL_REGEX.findall(text)
if not urls:
await message.reply_text("Send a direct OTT/video URL.")
return


url = urls[0]
if not is_allowed_url(url):
await message.reply_text("This domain is not in the allowed list. Add it to ALLOWED_DOMAINS in the code if needed.")
return


progress = await message.reply_text("Preparing to download...")


# Create a temporary directory
with tempfile.TemporaryDirectory() as tmpdir:
try:
filepath = await asyncio.get_event_loop().run_in_executor(None, lambda: asyncio.run_coroutine_threadsafe(asyncio.to_thread(lambda: download_with_ytdl_sync(url, tmpdir, progress)), asyncio.get_event_loop()).result())
except Exception as e:
# fallback: run sync download in blocking executor using yt-dlp directly
try:
filepath = await asyncio.get_event_loop().run_in_executor(None, lambda: download_with_ytdl_sync_blocking(url, tmpdir, progress))
except Exception as e2:
await progress.edit_text(f"Failed to download: {e2}")
return


# check size
try:
size = Path(filepath).stat().st_size
if size > MAX_BYTES:
await progress.edit_text(f"Downloaded file is too large ({size//1024//1024} MB). Max is {MAX_FILE_SIZE_MB} MB.")
# Optionally: upload to external hosting here
return


await progress.edit_text("Uploading to Telegram...")
await client.send_document(message.chat.id, document=filepath, caption=f"Downloaded from: {url}")
await progress.delete()
except Exception as e:
await progress.edit_text(f"Error sending file: {e}")




# Helper synchronous wrappers to use yt-dlp in executors
from yt_dlp import YoutubeDL, DownloadError


def download_with_ytdl_sync_blocking(url: str, download_dir: str, progress_msg: Message):
ytdl_opts = YTDL_OPTS_BASE.copy()
ytdl_opts['outtmpl'] = str(Path(download_dir) / '%(title).200s.%(ext)s')
# keep simple (no progress hook in this blocking path)
with YoutubeDL(ytdl_opts) as ytdl:
info = ytdl.extract_info(url, download=False)
formats = info.get('formats') or []
if not formats:
raise RuntimeError('No downloadable formats detected (possible DRM or protected stream)')
ytdl.download([url])
files = list(Path(download_dir).glob('*'))
if not files:
raise RuntimeError('Download completed but file not found')
latest = max(files, key=lambda p: p.stat().st_mtime)
return str(latest)




# Minimal safe wrapper to call from async
def download_with_ytdl_sync(url: str, download_dir: str, progress_msg: Message):
return download_with_ytdl_sync_blocking(url, download_dir, progress_msg)




if __name__ == '__main__':
app.run()
