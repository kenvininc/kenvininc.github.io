#!/bin/sh
# KHÔI PHỤC database + ảnh từ bản sao lưu. GHI ĐÈ dữ liệu hiện tại.
#   sudo sh scripts/restore.sh backups/db-20261016-0200.dump backups/media-20261016-0200.tar.gz
# Trước khi chạy: nên sao lưu trạng thái hiện tại bằng scripts/backup.sh.
set -eu
cd "$(dirname "$0")/.."
. ./.env
DB_FILE="${1:?Thiếu file .dump}"
MEDIA_FILE="${2:-}"
[ -f "$DB_FILE" ] || { echo "Không thấy $DB_FILE"; exit 1; }

echo "Thao tác này sẽ GHI ĐÈ database ${POSTGRES_DB} và thư mục ảnh hiện tại."
printf "Gõ KHOI PHUC để tiếp tục: "
read -r ANSWER
[ "$ANSWER" = "KHOI PHUC" ] || { echo "Đã hủy."; exit 1; }

echo "Dừng web để không có đơn mới trong lúc khôi phục..."
docker compose stop web nginx

echo "Khôi phục database..."
docker exec -i kenvinshop-db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner < "$DB_FILE"

if [ -n "$MEDIA_FILE" ]; then
  echo "Khôi phục ảnh (thư mục cũ đổi tên thành data/media.truoc-khoi-phuc-*)..."
  [ -d data/media ] && mv data/media "data/media.truoc-khoi-phuc-$(date +%Y%m%d-%H%M)"
  mkdir -p data
  tar -xzf "$MEDIA_FILE" -C data
fi

docker compose start web nginx
echo "Xong. Kiểm tra cửa hàng và trang quản trị."
