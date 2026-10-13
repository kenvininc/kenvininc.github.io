FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py entrypoint.sh ./
COPY static ./static

EXPOSE 8000
# Chạy qua sh để không phụ thuộc quyền execute (upload từ Windows sẽ mất chmod +x)
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
