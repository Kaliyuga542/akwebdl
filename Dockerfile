FROM python:3.11-slim

# System dependencies install
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install N_m3u8DL-RE
RUN wget https://github.com/nilaoda/N_m3u8DL-RE/releases/latest/download/N_m3u8DL-RE_Beta_linux-x64.zip -O /tmp/nm.zip && \
    unzip /tmp/nm.zip -d /tmp/nm && \
    mv /tmp/nm/N_m3u8DL-RE_Beta_linux-x64/N_m3u8DL-RE /usr/local/bin/ && \
    chmod +x /usr/local/bin/N_m3u8DL-RE && \
    rm -rf /tmp/nm /tmp/nm.zip

# Debug check (optional: can be removed later)
RUN which N_m3u8DL-RE && N_m3u8DL-RE --version || echo "N_m3u8DL-RE not found!"

# Set workdir
WORKDIR /workspace

# Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot source
COPY main.py .

# Start bot
CMD ["python", "main.py"]
