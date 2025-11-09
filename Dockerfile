FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN apt update && apt install -y ffmpeg && \
    pip install -r requirements.txt

# Expose health port for Koyeb health checks
EXPOSE 8000

# Run both the bot and health server concurrently
CMD bash -c "python3 health_server.py & python3 main.py"
