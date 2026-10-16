#!/bin/sh
# Sao lưu database + ảnh upload của Kenvin Shop.
# Chạy trong thư mục project (nơi có docker-compose.yml và .env), cần quyền chạy docker:
#   sudo sh scripts/backup.sh
# Kết quả: backups/db-YYYYmmdd-HHMM.dump và backups/media-YYYYmmdd-HHMM.tar.gz
# KEEP_DAYS: số ngày giữ bản sao lưu (mặc định 30).
set -eu
cd "$(dirname "$0")/.."
. ./.env
KEEP_DAYS="${KEEP_DAYS:-30}"
STAMP="$(date +%Y%m%d-%H%M)"
OUT="backups"
mkdir -p "$OUT"

echo "Sao lưu database..."
docker exec kenvinshop-db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$OUT/db-$STAMP.dump.tmp"
mv "$OUT/db-$STAMP.dump.tmp" "$OUT/db-$STAMP.dump"

echo "Sao lưu ảnh upload..."
tar -czf "$OUT/media-$STAMP.tar.gz.tmp" -C data media
mv "$OUT/media-$STAMP.tar.gz.tmp" "$OUT/media-$STAMP.tar.gz"

# Kiểm tra file dump đọc được
docker exec -i kenvinshop-db pg_restore --list < "$OUT/db-$STAMP.dump" > /dev/null

find "$OUT" -name 'db-*.dump' -mtime +"$KEEP_DAYS" -delete
find "$OUT" -name 'media-*.tar.gz' -mtime +"$KEEP_DAYS" -delete
ls -lh "$OUT/db-$STAMP.dump" "$OUT/media-$STAMP.tar.gz"
echo "Xong. Nhớ chép thư mục backups/ sang nơi khác (Hyper Backup, NAS khác, cloud)."
