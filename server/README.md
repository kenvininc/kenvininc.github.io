# fb-download

Web + API tải video Facebook (FastAPI + yt-dlp + ffmpeg), chạy trên Synology Container Manager.
Dùng qua web `https://dl.kenvin.biz/` hoặc iOS Shortcut.

```
iPhone ──HTTPS──> Cloudflare ──> router :443 ──> nginx 192.168.1.48 ──HTTP──> NAS 192.168.1.45:8686
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

### 2.1 Kiểm tra trước

Từ máy nginx (192.168.1.48):

```
curl http://192.168.1.45:8686/api/health
```

Phải ra `{"ok":true,...}`. Nếu không được thì kiểm tra DSM firewall
(Control Panel → Security → Firewall) có chặn 8686 không.
Nên giới hạn 8686 chỉ cho 192.168.1.48 vào.

### 2.2 Cloudflare DNS (`kenvin.biz`)

DNS → Records → Add record:
- Type `A`, Name `dl`, IPv4 = IP public của mạng có nginx, Proxy status **Proxied** (mây cam).
- Nếu đã có subdomain khác trỏ về cùng nginx này thì dùng cùng IP đó
  (hoặc `CNAME dl → subdomain đó`).

SSL/TLS → mode **Full (strict)** nếu nginx có certificate hợp lệ cho `dl.kenvin.biz`
(Let's Encrypt hoặc Cloudflare Origin Certificate). Không dùng **Flexible**.

Giới hạn khi để Proxied:
- Cloudflare trả **524** nếu origin không trả byte nào trong 100 giây. API này tải xong video
  rồi mới trả file, nên video quá dài có thể bị 524. Video/Reels thông thường không bị.
- Bot Fight Mode / Security Level cao có thể trả trang challenge cho Shortcut
  (Shortcut không phải trình duyệt). Shortcut nhận về HTML thay vì video thì kiểm tra Security → Events.

### 2.3 Nginx 192.168.1.48

**Nginx Proxy Manager**: Add Proxy Host
- Domain: `dl.kenvin.biz`
- Scheme `http`, Forward Hostname `192.168.1.45`, Port `8686`
- Block Common Exploits: bật
- SSL: chọn/cấp certificate cho `dl.kenvin.biz`, bật Force SSL
- Advanced → Custom Nginx Configuration:

```
proxy_read_timeout 300s;
proxy_send_timeout 300s;
proxy_buffering off;
```

**Nginx thường**:

```nginx
server {
    listen 443 ssl;
    server_name dl.kenvin.biz;

    ssl_certificate     /path/to/dl.kenvin.biz/fullchain.pem;
    ssl_certificate_key /path/to/dl.kenvin.biz/privkey.pem;

    location / {
        proxy_pass http://192.168.1.45:8686;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_buffering off;
    }
}
```

`nginx -t` trước, OK rồi mới `nginx -s reload` (reload không làm rớt các site đang chạy,
nhưng config lỗi thì reload sẽ không áp dụng).

`proxy_buffering off` để nginx đẩy file thẳng về client, không ghi tạm ra disk của máy nginx.

### 2.4 Test

Từ 4G (ngoài LAN): `https://dl.kenvin.biz/api/health`.

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
