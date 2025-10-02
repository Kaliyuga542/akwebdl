FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y wget unzip curl ffmpeg && rm -rf /var/lib/apt/lists/*

# Install N_m3u8DL-RE
RUN wget https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.2.0/N_m3u8DL-RE_Linux_x64_Release.zip -O /tmp/nm3u8dl.zip \
    && unzip /tmp/nm3u8dl.zip -d /tmp/nm3u8dl \
    && mv /tmp/nm3u8dl/N_m3u8DL-RE /usr/local/bin/N_m3u8DL-RE \
    && chmod +x /usr/local/bin/N_m3u8DL-RE \
    && rm -rf /tmp/nm3u8dl /tmp/nm3u8dl.zip

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

EXPOSE 8080

# Run the bot
CMD ["python", "main.py"]
