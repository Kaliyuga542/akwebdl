FROM python:3.11-slim

# ffmpeg + wget install
RUN apt-get update && \
    apt-get install -y ffmpeg wget unzip && \
    rm -rf /var/lib/apt/lists/*

# Install N_m3u8DL-RE
RUN wget https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.2.0/N_m3u8DL-RE_Beta_linux-x64.zip -O /tmp/nm.zip && \
    unzip /tmp/nm.zip -d /usr/local/bin && \
    chmod +x /usr/local/bin/N_m3u8DL-RE && \
    rm /tmp/nm.zip

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
