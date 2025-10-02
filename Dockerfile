FROM ubuntu:22.04

# Install dependencies
RUN apt-get update && apt-get install -y \
    wget unzip curl ffmpeg mkvtoolnix libicu-dev \
    && rm -rf /var/lib/apt/lists/*

# Install N_m3u8DL-RE (Linux x64 binary)
RUN wget https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.2.0/N_m3u8DL-RE_Linux-x64_Release.zip -O /tmp/nm3u8dl.zip \
    && unzip /tmp/nm3u8dl.zip -d /usr/local/bin/ \
    && mv /usr/local/bin/N_m3u8DL-RE* /usr/local/bin/N_m3u8DL-RE \
    && chmod +x /usr/local/bin/N_m3u8DL-RE \
    && rm -rf /tmp/nm3u8dl.zip

# Install shaka-packager
RUN wget https://github.com/shaka-project/shaka-packager/releases/download/v3.0.1/packager-linux-x64 \
    -O /usr/local/bin/shaka-packager \
    && chmod +x /usr/local/bin/shaka-packager

# Install bento4 tools
RUN mkdir -p /tmp/bento && cd /tmp/bento \
    && wget https://files.videohelp.com/u/301890/bento4_tools_android.zip \
    && unzip bento4_tools_android.zip \
    && chmod +x * \
    && cp * /usr/local/bin/ \
    && cd / && rm -rf /tmp/bento

# Set working dir
WORKDIR /app

# Python setup
RUN apt-get update && apt-get install -y python3 python3-pip
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

CMD ["python3", "main.py"]
