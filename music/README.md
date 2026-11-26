# Dailoc Music (music.dailoc.dev)

Web nghe nhạc tự host trên NAS: upload nhạc từ điện thoại/PC, nghe online, chạy nền trên điện thoại, điều khiển từ lock screen / Control Center / CarPlay (màn hình Now Playing + nút trên vô lăng).

- Node.js 22 + Express, chạy trong Docker, 1 container, không cần database.
- File nhạc nằm thẳng trên share của NAS (`MUSIC_PATH`). Bỏ nhạc vào share qua SMB cũng được, app tự quét (lúc khởi động, mỗi `RESCAN_MINUTES` phút, hoặc bấm "Quét lại thư viện").
- Upload qua web vào `MUSIC_PATH/Uploads/`.
- Đăng nhập 1 mật khẩu (`APP_PASSWORD`), cookie HttpOnly giữ 180 ngày. Login giới hạn 10 lần sai / 15 phút / IP.
- Stream có HTTP Range (tua được, iOS bắt buộc cần cái này).
- Hỗ trợ: mp3, m4a/aac, flac, wav, aiff, ogg/opus. Trên iPhone, chắc ăn nhất là **mp3 / m4a (AAC)**. FLAC thường chạy được trên iOS mới, ogg/opus tùy phiên bản iOS. App không transcode.

## Cài đặt trên NAS (Synology Container Manager)

Cấu hình nằm hết trong `docker-compose.yml` (không dùng `.env`), giống các project khác trên NAS.

1. Giải nén zip vào thư mục project, ví dụ `/volume1/docker/music` (nên tránh `/volume1/web` nếu Web Station có thể serve thư mục đó, vì compose chứa mật khẩu).
2. File Station: tạo thư mục `data` trong thư mục project. Thư mục nhạc (vd shared folder `/volume1/music`) phải tồn tại sẵn.
3. Sửa `docker-compose.yml`:

| Chỗ cần sửa | Ý nghĩa |
|---|---|
| `user: "1026:100"` | uid:gid của user DSM có quyền ghi thư mục nhạc và `data` (SSH: `id <user>`) |
| `APP_PASSWORD` | Mật khẩu đăng nhập web. Có `$` thì viết `$$` |
| `ports: "8789:3000"` | Đổi số bên trái nếu 8789 đã bị dùng |
| `/volume1/music:/music` | Đường dẫn thư mục nhạc thật |
| `MAX_UPLOAD_MB`, `RESCAN_MINUTES`, `SESSION_DAYS` | Tùy chọn |

4. Container Manager → Project → Create → chọn thư mục project, dùng `docker-compose.yml` có sẵn → Build.
5. Log có `Dailoc Music listening on :3000` và `Scan done: N tracks` là ổn. Thử nội bộ: `http://<IP-NAS>:8789`.

Update sau này: thay file mới vào thư mục project (giữ nguyên `data/` và compose đã sửa), rồi Project → Action → Build lại.

## Public ra music.dailoc.dev

**Bắt buộc HTTPS** (iOS cần HTTPS cho "Add to Home Screen" chuẩn, và cookie login được set `Secure` khi đi qua HTTPS).

Chọn 1 trong các cách, tùy NAS đang dùng gì:

**Synology Reverse Proxy** (Control Panel → Login Portal → Advanced → Reverse Proxy):
- Source: HTTPS, `music.dailoc.dev`, port 443
- Destination: HTTP, `localhost`, port `8789`
- Cert Let's Encrypt cho `music.dailoc.dev` (Control Panel → Security → Certificate), gán vào entry này.

**Nginx / Nginx Proxy Manager**, phần quan trọng:

```nginx
client_max_body_size 600m;       # >= MAX_UPLOAD_MB
proxy_request_buffering off;     # upload file lớn không bị buffer hết vào disk proxy
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

**Cloudflare Tunnel**: trỏ `music.dailoc.dev` → `http://<IP-NAS>:8789`. Lưu ý gói Free giới hạn body request khoảng 100 MB, app đã upload từng file một nên mp3/m4a bình thường không bị ảnh hưởng, chỉ file FLAC/WAV rất lớn mới dính.

App tin header `X-Forwarded-*` từ proxy trong LAN/localhost (mặc định). `TRUST_PROXY` nhận số hop (`"1"`, `"2"`), `"true"`, hoặc danh sách IP/subnet. Chỉ ảnh hưởng IP dùng cho giới hạn đăng nhập sai.

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
└── docker-compose.yml
```
