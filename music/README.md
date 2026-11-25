# Dailoc Music (music.dailoc.dev)

Web nghe nhạc tự host trên NAS: upload nhạc từ điện thoại/PC, nghe online, chạy nền trên điện thoại, điều khiển từ lock screen / Control Center / CarPlay (màn hình Now Playing + nút trên vô lăng).

- Node.js 22 + Express, chạy trong Docker, 1 container, không cần database.
- File nhạc nằm thẳng trên share của NAS (`MUSIC_PATH`). Bỏ nhạc vào share qua SMB cũng được, app tự quét (lúc khởi động, mỗi `RESCAN_MINUTES` phút, hoặc bấm "Quét lại thư viện").
- Upload qua web vào `MUSIC_PATH/Uploads/`.
- Đăng nhập 1 mật khẩu (`APP_PASSWORD`), cookie HttpOnly giữ 180 ngày. Login giới hạn 10 lần sai / 15 phút / IP.
- Stream có HTTP Range (tua được, iOS bắt buộc cần cái này).
- Hỗ trợ: mp3, m4a/aac, flac, wav, aiff, ogg/opus. Trên iPhone, chắc ăn nhất là **mp3 / m4a (AAC)**. FLAC thường chạy được trên iOS mới, ogg/opus tùy phiên bản iOS. App không transcode.

## Cài đặt trên NAS

Cần SSH vào NAS (hoặc dùng Container Manager / Portainer với nội dung `docker-compose.yml` tương tự).

```bash
git clone -b claude/eager-faraday-hxtks0 https://github.com/kenvininc/kenvininc.github.io.git
cd kenvininc.github.io/music
cp .env.example .env
```

Sửa `.env`:

| Biến | Ý nghĩa |
|---|---|
| `APP_PASSWORD` | Mật khẩu đăng nhập (bắt buộc, đặt dài) |
| `MUSIC_PATH` | Đường dẫn share nhạc trên NAS, vd `/volume1/music` |
| `PUID` / `PGID` | UID/GID có quyền đọc ghi `MUSIC_PATH` (`id <user>` để xem) |
| `HOST_PORT` | Port publish ra ngoài, mặc định `8095` |
| `MAX_UPLOAD_MB` | Giới hạn mỗi file upload, mặc định 500 |
| `RESCAN_MINUTES` | Tự quét lại thư mục nhạc (0 = tắt) |

```bash
mkdir -p data
sudo chown ${PUID}:${PGID} data     # thay bằng số thật, vd: sudo chown 1026:100 data
docker compose up -d --build
docker compose logs -f
```

Thấy dòng `Dailoc Music listening on :3000` và `Scan done: N tracks` là ổn. Thử nội bộ: `http://<IP-NAS>:8095`.

Update sau này:

```bash
git pull
docker compose up -d --build
```

## Public ra music.dailoc.dev

**Bắt buộc HTTPS** (iOS cần HTTPS cho "Add to Home Screen" chuẩn, và cookie login được set `Secure` khi đi qua HTTPS).

Chọn 1 trong các cách, tùy NAS đang dùng gì:

**Synology Reverse Proxy** (Control Panel → Login Portal → Advanced → Reverse Proxy):
- Source: HTTPS, `music.dailoc.dev`, port 443
- Destination: HTTP, `localhost`, port `8095`
- Cert Let's Encrypt cho `music.dailoc.dev` (Control Panel → Security → Certificate), gán vào entry này.

**Nginx / Nginx Proxy Manager**, phần quan trọng:

```nginx
client_max_body_size 600m;       # >= MAX_UPLOAD_MB
proxy_request_buffering off;     # upload file lớn không bị buffer hết vào disk proxy
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

**Cloudflare Tunnel**: trỏ `music.dailoc.dev` → `http://<IP-NAS>:8095`. Lưu ý gói Free giới hạn body request khoảng 100 MB, app đã upload từng file một nên mp3/m4a bình thường không bị ảnh hưởng, chỉ file FLAC/WAV rất lớn mới dính.

App tin header `X-Forwarded-*` từ IP private (`TRUST_PROXY` mặc định `loopback, linklocal, uniquelocal`). Nếu proxy nằm ở IP public khác thì set `TRUST_PROXY` cho đúng.

## Dùng trên iPhone + CarPlay

1. Mở Safari → `https://music.dailoc.dev` → đăng nhập.
2. Share → **Add to Home Screen** để có icon như app.
3. Bấm phát 1 bài (lần đầu phải bấm tay, iOS không cho tự phát).
4. Khóa màn hình / chuyển app khác: nhạc vẫn chạy, hết bài tự sang bài tiếp.
5. Lên xe cắm CarPlay: vào **Now Playing** trên màn hình CarPlay để play/pause/next/prev; nút next/prev trên vô lăng cũng gửi lệnh vào app.

### Giới hạn thật sự với CarPlay

- Web app **không thể có icon riêng trên màn hình CarPlay**, cũng không duyệt thư viện / chọn bài trên màn hình xe được. Apple chỉ cho app native (có entitlement CarPlay Audio) làm việc đó. Phải chọn bài/playlist trên điện thoại trước, sau đó trên xe chỉ điều khiển play/pause/next/prev/tua qua Now Playing.
- App đăng ký Media Session `nexttrack`/`previoustrack` và cố ý **không** đăng ký `seekforward`/`seekbackward`, để iOS hiện nút Next/Prev thay vì nút tua ±10s.
- Hành vi iOS với web app chạy nền có thay đổi qua các bản iOS. Nếu mở từ icon Home Screen mà khóa máy bị tắt tiếng, thử mở bằng tab Safari thường xem có khác không.

Nếu cần **CarPlay đầy đủ** (duyệt album/bài ngay trên màn hình xe): dùng Navidrome (Docker, Subsonic API) trỏ vào cùng thư mục nhạc, và nghe bằng app iOS hỗ trợ CarPlay như Amperfy hoặc play:Sub. Web này vẫn dùng song song để upload được vì cả hai đọc chung `MUSIC_PATH`.

## Backup / dữ liệu

- Nhạc: nằm ở `MUSIC_PATH` trên NAS, backup theo share đó.
- `./data`: `library.json` (cache metadata), `covers/` (ảnh bìa), `session.secret`. Mất thư mục này không mất nhạc, app quét lại là có; chỉ phải đăng nhập lại.
- Nút xoá trong app **xoá hẳn file trên NAS**. Bật Recycle Bin / snapshot cho share nếu muốn có đường lui.

## Cấu trúc

```
music/
├── server.js            # API: login, upload, list, stream (Range), cover, scan
├── public/              # PWA: index.html, app.js, style.css, manifest, icons
├── Dockerfile
├── docker-compose.yml
└── .env.example
```
