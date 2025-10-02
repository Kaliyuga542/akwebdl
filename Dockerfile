FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget ffmpeg curl unzip \
    && rm -rf /var/lib/apt/lists/*

# Install N_m3u8DL-RE Linux binary
RUN wget -O /usr/local/bin/N_m3u8DL-RE \
    https://github.com/nilaoda/N_m3u8DL-RE/releases/latest/download/N_m3u8DL-RE_Linux \
    && chmod +x /usr/local/bin/N_m3u8DL-RE

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create downloads folder
RUN mkdir -p /app/downloads

# Run the bot
CMD ["python", "main.py"]
