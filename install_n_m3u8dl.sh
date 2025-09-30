#!/bin/bash
set -e

# Install N_m3u8DL-RE if not present
if [ ! -f /usr/local/bin/N_m3u8DL-RE ]; then
    wget https://github.com/nilaoda/N_m3u8DL-RE/releases/latest/download/N_m3u8DL-RE-linux-x64 -O /usr/local/bin/N_m3u8DL-RE
    chmod +x /usr/local/bin/N_m3u8DL-RE
fi

python3 main.py
