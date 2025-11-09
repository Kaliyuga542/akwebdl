# ----------------------------------------
# 📺 Telegram Live TV Recorder Bot
# ----------------------------------------

# 🐍 Use an official lightweight Python image
FROM python:3.10-slim

# 🧰 Install system dependencies (ffmpeg + clean-up)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# 📂 Create app directory
WORKDIR /app

# 📝 Copy requirements first (for efficient Docker caching)
COPY requirements.txt .

# 📦 Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 📁 Copy the rest of your app
COPY . .

# ✅ Environment variables (optional defaults)
ENV PYTHONUNBUFFERED=1

# 🚀 Command to run the bot
CMD ["python3", "main.py"]
