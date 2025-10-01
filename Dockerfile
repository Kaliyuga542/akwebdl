FROM python:3.11-slim
RUN apt-get update && apt-get install -y ffmpeg wget unzip
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
CMD ["python", "main.py"]
