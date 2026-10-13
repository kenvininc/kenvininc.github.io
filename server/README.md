# fb-download

Web + API tải video Facebook (FastAPI + yt-dlp + ffmpeg), chạy trên Synology Container Manager.
Dùng qua web `https://dl.kenvin.biz/` hoặc iOS Shortcut.

```
iPhone ──HTTPS──> dl.kenvin.biz (DSM Reverse Proxy) ──> fb-download:8686 ──> Facebook
```

## API

| Method | Path | Ghi chú |
|---|---|---|
| GET | `/` | Trang web |
| GET | `/api/health` | Kiểm tra server + version yt-dlp |
| POST | `/api/download` | Body `{"url": "..."}`, header `X-API-Key` → trả file mp4 |
| GET | `/api/download?url=...` | Như trên, header `X-API-Key` |

Chỉ nhận link `facebook.com`, `fb.watch`, `fb.com` (kể cả subdomain như `m.`, `web.`).

## 1. Deploy lên Synology

1. File Station: tạo thư mục `/volume1/docker/fb-download`, copy các file trong `server/` vào đó
   (`app.py`, `requirements.txt`, `Dockerfile`, `entrypoint.sh`, `docker-compose.yml`, thư mục `static/`).
2. Tạo file `.env` từ `.env.example`, đổi `API_KEY` thành chuỗi random dài
   (ví dụ chạy `openssl rand -hex 24` trên máy bất kỳ).
3. Tạo thư mục con `data/` (để trống, chỉ dùng khi cần cookies).
4. Container Manager → **Project** → **Create**
   - Project name: `fb-download`
   - Path: `/volume1/docker/fb-download`
   - Source: *Use existing docker-compose.yml*
   - Next → Done. Lần đầu sẽ build image (cài ffmpeg), mất vài phút.
5. Kiểm tra trong LAN: mở `http://<IP-NAS>:8686/api/health`, phải ra `{"ok":true,...}`.
   Mở `http://<IP-NAS>:8686/` phải thấy trang web.

Port 8686 là port host, nếu trùng với project khác thì đổi trong `docker-compose.yml`.

## 2. Publish ra `dl.kenvin.biz`

iOS Safari cần HTTPS cho share sheet, và API key đi trong header, nên bắt buộc HTTPS.

**DNS** (tại nơi quản lý DNS của `kenvin.biz`):
- NAS có IP public tĩnh: record `A` `dl` → IP public đó.
- IP public động: record `CNAME` `dl` → hostname DDNS của NAS
  (DSM: Control Panel → External Access → DDNS, ví dụ `xxx.synology.me`).
- Kiểm tra: `nslookup dl.kenvin.biz` phải ra đúng IP public của mạng có NAS.

**Router/firewall**: forward TCP 443 (và 80 nếu cấp Let's Encrypt qua HTTP challenge) về NAS.
Không cần mở 8686 ra ngoài.

**Reverse proxy**: DSM 7 → Control Panel → Login Portal → Advanced → Reverse Proxy → Create
- Source: `HTTPS`, hostname `dl.kenvin.biz`, port `443`
- Destination: `HTTP`, `localhost`, port `8686`
- Nếu có phần timeout trong Advanced Settings của rule: tăng lên ~300s,
  vì video dài có thể tải lâu hơn timeout mặc định của proxy.

**Certificate**: Control Panel → Security → Certificate → Add → Let's Encrypt cho `dl.kenvin.biz`,
rồi Settings → gán certificate này cho reverse proxy `dl.kenvin.biz`.

Kiểm tra từ 4G (ngoài LAN): `https://dl.kenvin.biz/api/health`.

## 3. Web

Mở `https://dl.kenvin.biz/` trên iPhone → **Cài đặt** → nhập API key → Lưu
(API URL để trống). Cài đặt nằm trong localStorage của Safari.

Dùng: paste link → **Tải video** → **Lưu vào Photos** → chọn **Save Video**.
Phải bấm 2 nút vì iOS chỉ cho mở share sheet ngay sau một lần tap.

Mẹo: Safari → Share → **Add to Home Screen** để dùng như app.

## 4. iOS Shortcut (lưu thẳng vào Photos, không cần bấm thêm)

Shortcuts → **+** → đặt tên ví dụ `FB Save`:

1. Bấm (i) → bật **Show in Share Sheet**, Receive: chỉ chọn **URLs** (và **Text**).
   If there's no input: **Get Clipboard**.
2. Action **Get Contents of URL**
   - URL: `https://dl.kenvin.biz/api/download`
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
| `ALLOWED_ORIGINS` | (trống) | CORS, chỉ cần khi web ở domain khác gọi API |
| `MAX_FILESIZE_MB` | `500` | Giới hạn dung lượng video |
| `MAX_CONCURRENT` | `2` | Số job tải đồng thời |
| `DOWNLOAD_TIMEOUT` | `300` | Giây |
| `YTDLP_AUTO_UPDATE` | `1` | Update yt-dlp mỗi lần container start |
| `COOKIES_FILE` | `/data/cookies.txt` | |
