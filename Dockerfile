FROM python:3.11-slim

# install system dependencies
RUN apt-get update && apt-get install -y ffmpeg wget unzip && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# copy requirements and install
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# copy source code
COPY . /app

# entrypoint
CMD ["python", "main.py"]
