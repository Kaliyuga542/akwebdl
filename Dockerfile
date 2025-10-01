FROM python:3.11-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install N_m3u8DL-RE
RUN wget https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.2.0/N_m3u8DL-RE_Beta_linux-x64.zip -O /tmp/nm.zip && \
    unzip /tmp/nm.zip -d /tmp/nm && \
    mv /tmp/nm/N_m3u8DL-RE_Beta_linux-x64/N_m3u8DL-RE /usr/local/bin/ && \
    chmod +x /usr/local/bin/N_m3u8DL-RE && \
    rm -rf /tmp/nm /tmp/nm.zip

# Set workdir
WORKDIR /workspace

# Install python libs
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot files
COPY main.py .

# Run bot
CMD ["python", "main.py"]
