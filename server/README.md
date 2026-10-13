# fb-download

Backend tải video Facebook (FastAPI + yt-dlp + ffmpeg), chạy trên Synology Container Manager.
Client dùng được: web `https://kenvin.me/fb/` hoặc iOS Shortcut.

```
iPhone ──HTTPS──> DSM Reverse Proxy ──> fb-download:8686 ──> Facebook
```

## API

| Method | Path | Ghi chú |
|---|---|---|
| GET | `/api/health` | Kiểm tra server + version yt-dlp |
| POST | `/api/download` | Body `{"url": "..."}`, header `X-API-Key` → trả file mp4 |
| GET | `/api/download?url=...` | Như trên, header `X-API-Key` |

Chỉ nhận link `facebook.com`, `fb.watch`, `fb.com` (kể cả subdomain như `m.`, `web.`).

## 1. Deploy lên Synology

1. File Station: tạo thư mục `/volume1/docker/fb-download`, copy các file trong `server/` vào đó
   (`app.py`, `requirements.txt`, `Dockerfile`, `entrypoint.sh`, `docker-compose.yml`).
2. Tạo file `.env` từ `.env.example`, đổi `API_KEY` thành chuỗi random dài
   (ví dụ chạy `openssl rand -hex 24` trên máy bất kỳ).
3. Tạo thư mục con `data/` (để trống, chỉ dùng khi cần cookies).
4. Container Manager → **Project** → **Create**
   - Project name: `fb-download`
   - Path: `/volume1/docker/fb-download`
   - Source: *Use existing docker-compose.yml*
   - Next → Done. Lần đầu sẽ build image (cài ffmpeg), mất vài phút.
5. Kiểm tra trong LAN: mở `http://<IP-NAS>:8686/api/health`, phải ra `{"ok":true,...}`.

Port 8686 là port host, nếu trùng với project khác thì đổi trong `docker-compose.yml`.

## 2. Publish ra Internet qua HTTPS

Web `kenvin.me` chạy HTTPS nên backend cũng phải là HTTPS (browser chặn mixed content).
Shortcut thì gọi được cả HTTP, nhưng vẫn nên dùng HTTPS vì API key đi trong header.

DSM 7: Control Panel → Login Portal → Advanced → **Reverse Proxy** → Create

- Source: `HTTPS`, hostname ví dụ `fb.<domain-của-anh>`, port `443`
- Destination: `HTTP`, `localhost`, port `8686`
- Nếu có phần timeout trong Advanced Settings của rule: tăng lên ~300s,
  vì video dài có thể tải lâu hơn timeout mặc định của proxy.

Sau đó:
- DNS: trỏ `fb.<domain>` về IP public của NAS (hoặc dùng DDNS của Synology).
- Certificate: Control Panel → Security → Certificate, cấp Let's Encrypt cho hostname này
  và gán cho reverse proxy rule.
- Router/firewall: chỉ cần mở 443 về NAS nếu chưa mở. Không cần mở 8686 ra ngoài.

## 3. Web

Mở `https://kenvin.me/fb/` trên iPhone → **Cài đặt server** → nhập API URL
(`https://fb.<domain>`) và API key → Lưu. Cài đặt nằm trong localStorage của Safari.

Dùng: paste link → **Tải video** → **Lưu vào Photos** → chọn **Save Video**.
Phải bấm 2 nút vì iOS chỉ cho mở share sheet ngay sau một lần tap.

Mẹo: Safari → Share → **Add to Home Screen** để dùng như app.

## 4. iOS Shortcut (lưu thẳng vào Photos, không cần bấm thêm)

Shortcuts → **+** → đặt tên ví dụ `FB Save`:

1. Bấm (i) → bật **Show in Share Sheet**, Receive: chỉ chọn **URLs** (và **Text**).
   If there's no input: **Get Clipboard**.
2. Action **Get Contents of URL**
   - URL: `https://fb.<domain>/api/download`
   - Method: `POST`
   - Headers: `X-API-Key` = `<API key>`
   - Request Body: `JSON`, field `url` (Text) = biến **Shortcut Input**
3. Action **Save to Photo Album** → Album: Recents. Input: **Contents of URL**.
4. (Tuỳ chọn) **Show Notification**: "Đã lưu video".

Dùng: trong app Facebook → Share → Copy link, hoặc Share → More → `FB Save`.
Nếu Facebook không hiện shortcut trong share sheet thì copy link rồi chạy shortcut
(nó sẽ lấy từ clipboard).

## 5. Khi tải không được

- Xem log: Container Manager → Container → `fb-download` → Log.
- Thường gặp nhất là yt-dlp cũ. Restart container sẽ tự update yt-dlp (`YTDLP_AUTO_UPDATE=1`).
- Video private / trong group / cần login: export cookies của một tài khoản Facebook
  (format Netscape `cookies.txt`, dùng extension kiểu "Get cookies.txt LOCALLY")
  rồi để vào `data/cookies.txt`. Backend tự dùng nếu file tồn tại.
  Nên dùng tài khoản phụ, vì cookie này có quyền như đang login tài khoản đó,
  và Facebook có thể khoá tài khoản nếu thấy hoạt động bất thường.
- Chỉ hỗ trợ video. Bài post chỉ có ảnh thì yt-dlp không tải được.

## Biến môi trường

| Biến | Mặc định | |
|---|---|---|
| `API_KEY` | (bắt buộc) | Key cho client |
| `ALLOWED_ORIGINS` | `https://kenvin.me` | CORS cho web frontend |
| `MAX_FILESIZE_MB` | `500` | Giới hạn dung lượng video |
| `MAX_CONCURRENT` | `2` | Số job tải đồng thời |
| `DOWNLOAD_TIMEOUT` | `300` | Giây |
| `YTDLP_AUTO_UPDATE` | `1` | Update yt-dlp mỗi lần container start |
| `COOKIES_FILE` | `/data/cookies.txt` | |
