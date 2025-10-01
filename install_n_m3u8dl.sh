#!/bin/bash
set -e

# Create bin folder inside project
mkdir -p bin
cd bin

# Download latest release (Linux x64)
wget -O N_m3u8DL-RE.zip https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.2.0/N_m3u8DL-RE_Beta_linux-x64.zip

# Unzip and set permission
unzip -o N_m3u8DL-RE.zip
chmod +x N_m3u8DL-RE

# Go back to project root
cd ..
