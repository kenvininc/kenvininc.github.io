# Triển khai Kenvin Shop lên Synology

Hướng dẫn viết cho NAS anh đã gửi ảnh: DSM 7.2.2-72806, PFVN-NAS, 192.168.1.45, Container Manager (cùng NAS đang chạy `fb-download`).

Chưa kiểm tra trên NAS thật: kiến trúc CPU (NAS ảo thường là x86_64), RAM còn trống, port 8687, quyền thư mục. Các image dùng (`python:3.12-slim`, `postgres:16-alpine`, `nginx:1.28-alpine`) có bản cho amd64 và arm64.

```
Khách ──HTTPS──> (Cloudflare) ──> router :443 ──> nginx 192.168.1.48 ──HTTP──> NAS 192.168.1.45:8687
                                                                              └ nginx container → web (gunicorn) → db (PostgreSQL)
```

Stack gồm 3 container:

| Container | Vai trò | Dữ liệu |
|---|---|---|
| `kenvinshop-db` | PostgreSQL 16 | `data/postgres` |
| `kenvinshop-web` | Django + gunicorn, tự chạy migrate khi khởi động | ảnh upload: `data/media` |
| `kenvinshop-nginx` | Mở port 8687, phục vụ `/static/` và `/media/` | |

Bộ nhớ ước tính: Postgres khoảng 50–150 MB, web 3 worker khoảng 200–300 MB. Đây là ước tính, chưa đo trên NAS.

## 1. Tạo project

1. File Station: tạo thư mục `/volume1/docker/kenvinshop`, copy toàn bộ nội dung thư mục `shop/` vào đó.
2. Tạo file `.env` từ `.env.example` và sửa các dòng sau:
   - `SECRET_KEY`: chuỗi ngẫu nhiên dài.
   - `POSTGRES_PASSWORD`: mật khẩu mạnh. Chỉ dùng chữ, số, `-`, `_` để script backup đọc được.
   - `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL`: theo domain của shop.

   Lệnh tạo chuỗi ngẫu nhiên (chạy trên máy nào cũng được):
   ```
   python3 -c "import secrets; print(secrets.token_urlsafe(50))"
   openssl rand -hex 24
   ```
3. Tạo các thư mục con `data/postgres`, `data/media`, `data/backup` (để trống).
4. Container Manager → **Project** → **Create**
   - Project name: `kenvinshop`
   - Path: `/volume1/docker/kenvinshop`
   - Source: *Use existing docker-compose.yml*
   - Next → Done. Lần đầu sẽ build image, mất vài phút.
5. Xem log: Container Manager → Container → `kenvinshop-web` → Log. Đúng thì sẽ thấy `migrate` chạy xong và dòng `Listening at: http://0.0.0.0:8000`.

Nếu port 8687 đã bị dùng, đổi `HTTP_PORT` trong `.env`.

**Test trong LAN trước khi có HTTPS:** tạm đặt `SECURE_COOKIES=0` và thêm `192.168.1.45` vào `ALLOWED_HOSTS`, thêm `http://192.168.1.45:8687` vào `CSRF_TRUSTED_ORIGINS`. Restart project, mở `http://192.168.1.45:8687/`. Test xong thì trả về `SECURE_COOKIES=1`.

## 2. Tạo tài khoản quản trị đầu tiên

Không có tài khoản mặc định. SSH vào NAS (Control Panel → Terminal & SNMP → bật SSH), rồi chạy:

```
sudo docker exec -it kenvinshop-web python manage.py create_owner --username <ten-dang-nhap>
```

Lệnh sẽ hỏi mật khẩu 2 lần (tối thiểu 10 ký tự, không quá phổ biến). Sau đó đăng nhập tại `/admin/`.

Các tài khoản nhân viên khác tạo trong Admin → Tài khoản.

## 3. Publish ra Internet

Cách làm giống `dl.kenvin.biz` (xem `server/README.md`): thêm proxy host trên nginx 192.168.1.48 trỏ về `http://192.168.1.45:8687`.

Nginx thường:

```nginx
server {
    listen 443 ssl;
    server_name shop.example.com;
    ssl_certificate     /path/fullchain.pem;
    ssl_certificate_key /path/privkey.pem;
    client_max_body_size 40m;

    location / {
        proxy_pass http://192.168.1.45:8687;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Nginx Proxy Manager: thêm `client_max_body_size 40m;` vào Advanced.

Chuyển HTTP → HTTPS làm ở nginx 192.168.1.48 (Force SSL) hoặc Cloudflare (Always Use HTTPS). Khi HTTPS đã chạy ổn định, có thể đặt `SECURE_HSTS_SECONDS=31536000` trong `.env`. Lưu ý: HSTS khó gỡ nếu sau này domain không còn HTTPS.

Chạy `nginx -t` trước, OK rồi mới reload. Upload nhiều ảnh cùng lúc cần `client_max_body_size` đủ lớn; mặc định nginx chỉ cho 1 MB.

### IP khách (`NUM_PROXIES`)

Django lấy IP khách từ `X-Forwarded-For` để giới hạn đăng nhập sai và tra cứu đơn. `NUM_PROXIES` là số proxy đứng trước Django:

| Đường đi | `NUM_PROXIES` |
|---|---|
| Truy cập thẳng `http://NAS:8687` | 1 |
| nginx 192.168.1.48 → NAS | 2 |
| Cloudflare (Proxied) → nginx 192.168.1.48 → NAS | 3 |

Đặt sai thì giới hạn theo IP có thể áp lên IP của proxy thay vì IP khách. Giới hạn theo tên đăng nhập vẫn hoạt động. Sau khi publish, kiểm tra cột IP ở Admin → Nhật ký thao tác: phải thấy IP public của mình, không phải 192.168.x.x hay IP Cloudflare.

## 4. Lịch chạy định kỳ (DSM Task Scheduler)

Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script, user `root`.

| Việc | Lịch | Lệnh |
|---|---|---|
| Sao lưu | Hằng ngày, ví dụ 02:15 | `cd /volume1/docker/kenvinshop && sh scripts/backup.sh` |
| Tự hủy đơn chuyển khoản quá hạn (chỉ khi đã bật trong Cấu hình) | Mỗi 30 phút | `docker exec kenvinshop-web python manage.py cancel_unpaid_orders` |

## 5. Backup và restore

`scripts/backup.sh` tạo 2 file trong `backups/`:
- `db-YYYYmmdd-HHMM.dump`: `pg_dump` dạng custom. Script tự kiểm tra file đọc được bằng `pg_restore --list`.
- `media-YYYYmmdd-HHMM.tar.gz`: toàn bộ ảnh upload.

Bản cũ hơn 30 ngày tự xóa (đổi bằng biến `KEEP_DAYS`). **Cần chép `backups/` sang nơi khác** (Hyper Backup sang NAS/ổ khác/cloud), vì backup nằm cùng NAS không cứu được khi NAS hỏng.

Không nên backup bằng cách copy thư mục `data/postgres` khi container đang chạy, vì file có thể không nhất quán.

Khôi phục (sẽ ghi đè dữ liệu hiện tại; nên chạy backup trước):

```
cd /volume1/docker/kenvinshop
sudo sh scripts/restore.sh backups/db-20261016-0215.dump backups/media-20261016-0215.tar.gz
```

Script hỏi xác nhận (gõ `KHOI PHUC`), dừng web, chạy `pg_restore --clean`, đổi tên thư mục ảnh cũ thành `data/media.truoc-khoi-phuc-*` rồi giải nén ảnh từ backup và chạy lại web.

Đã test trong môi trường phát triển: xóa đơn và ảnh, chạy restore, đơn và ảnh trở lại đúng. Nên test lại restore trên NAS bằng một bản copy trước khi cần dùng thật.

## 6. Cập nhật phiên bản

1. Chạy backup (mục 5).
2. Chép code mới đè lên `/volume1/docker/kenvinshop`. **Không** xóa `.env` và `data/`.
3. Container Manager → Project `kenvinshop` → Action → **Build** (hoặc Stop → Build → Start). Lệnh tương đương:
   `sudo docker compose up -d --build`
4. Khi container `web` khởi động sẽ tự chạy migration. Xem log để chắc không có lỗi.
5. Nếu lỗi: khôi phục code cũ, build lại, rồi restore database từ bản backup ở bước 1 (vì migration có thể đã đổi schema).

## 7. Khi có sự cố

- Xem log: Container Manager → Container → `kenvinshop-web` / `kenvinshop-nginx` → Log.
- Lỗi 400 Bad Request: domain chưa có trong `ALLOWED_HOSTS`.
- Lỗi 403 CSRF khi đăng nhập: thiếu `CSRF_TRUSTED_ORIGINS`, hoặc đang test qua HTTP mà `SECURE_COOKIES=1`.
- Upload ảnh lỗi 413: tăng `client_max_body_size` ở nginx 192.168.1.48.
- Log không ghi mật khẩu. Nhật ký đơn hàng chỉ ghi mã đơn, không ghi thông tin khách.
