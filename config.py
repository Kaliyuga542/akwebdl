# config.py
import os
from dotenv import load_dotenv
load_dotenv()


BOT_TOKEN = os.getenv('BOT_TOKEN') or ''
API_ID = os.getenv('API_ID') or '0'
API_HASH = os.getenv('API_HASH') or ''
OWNER_ID = int(os.getenv('OWNER_ID') or 0)
# Maximum file size in MB that bot will attempt to send to Telegram
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB') or 45)


if not BOT_TOKEN or API_ID == '0' or not API_HASH:
raise RuntimeError('Please set BOT_TOKEN, API_ID and API_HASH in environment variables')
