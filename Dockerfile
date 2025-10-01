# Use lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy rest of the code
COPY . /app/

# Install N_m3u8DL-RE
RUN chmod +x install_n_m3u8dl.sh && ./install_n_m3u8dl.sh

# Ensure binary is executable
RUN chmod +x /app/bin/N_m3u8DL-RE

# Run the bot
CMD ["python", "main.py"]
