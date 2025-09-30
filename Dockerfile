FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install N_m3u8DL-RE
RUN apt-get update && apt-get install -y wget && \
    wget https://github.com/nilaoda/N_m3u8DL-RE/releases/latest/download/N_m3u8DL-RE-linux-x64 -O /usr/local/bin/N_m3u8DL-RE && \
    chmod +x /usr/local/bin/N_m3u8DL-RE && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy bot code
COPY . .

CMD ["python", "main.py"]