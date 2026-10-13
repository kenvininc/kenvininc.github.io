#!/bin/sh
# Facebook hay đổi, yt-dlp cũ sẽ hỏng nhanh. Update mỗi lần start, lỗi thì vẫn chạy bản đang có.
if [ "${YTDLP_AUTO_UPDATE:-1}" = "1" ]; then
    pip install --no-cache-dir -q -U yt-dlp || echo "yt-dlp update failed, using installed version"
fi
exec uvicorn app:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
