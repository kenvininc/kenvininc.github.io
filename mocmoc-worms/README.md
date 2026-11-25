# mocmoc worms

Game rắn/giun nhiều người chơi trên trình duyệt, cùng thể loại với các game `.io`. Server Node.js chạy trong một container Docker duy nhất, phục vụ cả web tĩnh và WebSocket.

```
Browser ──HTTPS/WSS──> Cloudflare ──> nginx (reverse proxy) ──HTTP/WS──> NAS :8788 ──> container :3000
```

## Tính năng

- Multiplayer realtime, server authoritative (25 tick/s). Client chỉ gửi góc lái + boost, nên không cheat tốc độ/va chạm được.
- Bot tự bù khi vắng người (`BOTS`), để vào lúc nào map cũng có rắn.
- Chuột để lái, giữ chuột trái/Space/W để tăng tốc. Phím ←/→ hoặc A/D cũng lái được.
- Mobile: chạm/kéo để lái, nút ⚡ hoặc chạm ngón thứ hai để tăng tốc.
- Bảng xếp hạng, minimap, kill feed, màn hình xem (spectate) khi chưa vào chơi.
- Băng thông khoảng 5–10 KB/s mỗi người chơi: protocol binary, chỉ gửi thứ trong tầm nhìn, food gửi theo delta.

## Cấu trúc

```
server/index.js     HTTP static + WebSocket + game loop, giới hạn kết nối/IP, rate limit
server/game.js      mô phỏng: di chuyển, va chạm (spatial grid), ăn, bot AI, snapshot
public/             client (canvas 2D, không framework, không CDN)
public/js/shared.js hằng số dùng chung server/client
test/smoke.mjs      test nhanh: khởi động server, join, nhận state
```

## Chạy thử trên máy

```bash
npm install
```

```bash
npm start
```

Mở `http://localhost:3000`. Chạy test bằng `npm test`.

## 1. Deploy lên Synology (Container Manager)

1. File Station: tạo `/volume1/docker/mocmoc-worms`, copy toàn bộ thư mục này vào
   (`Dockerfile`, `docker-compose.yml`, `package.json`, `package-lock.json`, `server/`, `public/`).
   Không cần copy `node_modules/`.
2. Container Manager → **Project** → **Create**
   - Project name: `mocmoc-worms`
   - Path: `/volume1/docker/mocmoc-worms`
   - Source: *Use existing docker-compose.yml*
   - Next → Done. Lần đầu build image (~1 phút, cần NAS ra được Docker Hub và npm registry).
3. Kiểm tra trong LAN: `http://<IP-NAS>:8788/healthz` phải ra `{"ok":true,...}`,
   `http://<IP-NAS>:8788/` phải thấy trang game và chơi được (truy cập qua IP thì same-origin nên WebSocket được phép).

Ghi chú:
- Port host `8788`. Nếu trùng project khác thì đổi trong `docker-compose.yml` (chỉ đổi số bên trái).
- Nếu Container Manager báo lỗi với `init`, `mem_limit` hoặc `logging` (DSM/compose bản cũ), xoá các dòng đó đi rồi build lại. Mình chưa kiểm tra trên DSM thật nên không chắc bản nào bị lỗi.
- Container chạy user `node` (non-root), có healthcheck `/healthz`.

### Cập nhật code

Copy đè file mới → Container Manager → Project `mocmoc-worms` → **Action → Build** (hoặc Stop → Build → Start).
Restart container sẽ làm mọi người đang chơi bị ngắt; client tự reconnect nhưng mất ván đang chơi.

## 2. Publish ra `mocmoc.dev`

`.dev` nằm trong HSTS preload list, nên trình duyệt **bắt buộc HTTPS**. Phải có certificate hợp lệ ở nginx (Let's Encrypt hoặc Cloudflare Origin Certificate).

### 2.1 Kiểm tra trước

Từ máy chạy nginx:

```bash
curl http://<IP-NAS>:8788/healthz
```

Không ra JSON thì kiểm tra DSM firewall (Control Panel → Security → Firewall). Nên chỉ cho IP của máy nginx vào port 8788.

### 2.2 Cloudflare DNS

- Record `A` cho `mocmoc.dev` (`@`) → IP public của mạng có nginx, **Proxied**.
- SSL/TLS mode **Full (strict)**. Không dùng Flexible.
- Network → **WebSockets: On** (mặc định là bật, nhưng nên kiểm tra lại).

### 2.3 Nginx

**Nginx Proxy Manager**: Add Proxy Host
- Domain: `mocmoc.dev`
- Scheme `http`, Forward Hostname `<IP-NAS>`, Port `8788`
- **Websockets Support: bật** (bắt buộc, thiếu cái này game không kết nối được)
- Block Common Exploits: bật
- SSL: certificate cho `mocmoc.dev`, bật Force SSL
- Advanced:

```
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
```

**Nginx thường**:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    server_name mocmoc.dev;

    ssl_certificate     /path/to/mocmoc.dev/fullchain.pem;
    ssl_certificate_key /path/to/mocmoc.dev/privkey.pem;

    location / {
        proxy_pass http://<IP-NAS>:8788;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

`map` đặt trong block `http {}` (nếu config đã có `$connection_upgrade` cho site khác thì không thêm lần nữa).
Chạy `nginx -t` trước, OK rồi mới `nginx -s reload`.

`proxy_set_header Host $host` cần thiết vì server kiểm tra Origin của WebSocket: same-origin luôn được phép, còn domain khác phải nằm trong `ALLOWED_ORIGINS`.

### Chạy dưới sub-path (ví dụ `mocmoc.dev/worms/`)

Client dùng đường dẫn tương đối nên chạy được dưới sub-path:

```nginx
location /worms/ {
    proxy_pass http://<IP-NAS>:8788/;   # dấu / cuối để bỏ prefix /worms
    # ... các header WebSocket như trên
}
```

URL phải có dấu `/` cuối (`/worms/`).

### 2.4 Test

Từ 4G (ngoài LAN): mở `https://mocmoc.dev/`, bấm Chơi. Góc dưới màn hình hiện ping và fps.
Ping ở đây là RTT thật từ browser → Cloudflare → nginx → NAS.

## Biến môi trường (`docker-compose.yml`)

| Biến | Mặc định | |
|---|---|---|
| `PORT` | `3000` | Port trong container |
| `WORLD_RADIUS` | `3000` | Bán kính map. Đông người thì tăng lên 4000–5000 |
| `BOTS` | `16` | Tổng số rắn tối thiểu; thiếu người thì bot bù. `0` = tắt bot |
| `MAX_PLAYERS` | `60` | Người chơi thật tối đa cùng lúc |
| `MAX_CONN_PER_IP` | `6` | Số kết nối WebSocket mỗi IP |
| `FOOD_DENSITY` | `9000` | Diện tích (unit²) cho mỗi viên thức ăn. Nhỏ hơn = nhiều thức ăn hơn |
| `TRUST_PROXY` | `0` (compose: `1`) | `1` = lấy IP client từ `CF-Connecting-IP` / `X-Forwarded-For` |
| `ALLOWED_ORIGINS` | (trống) | Domain được phép mở WebSocket ngoài same-origin, ví dụ `https://mocmoc.dev`. `*` = tất cả |

Lưu ý `TRUST_PROXY=1`: nếu port 8788 mở thẳng ra Internet (không qua nginx) thì client có thể giả header IP để lách giới hạn kết nối/IP. Port 8788 chỉ nên mở cho máy nginx.

## Theo dõi

- `GET /healthz`: số client, số người đang chơi, bot, food, tick.
- Log: Container Manager → Container → `mocmoc-worms` → Log. Nếu server bị chậm (một tick > 40 ms) sẽ có dòng `[perf] N slow ticks in last 60s`.
- Hiệu năng đo trên Xeon 2.1 GHz: khoảng 0.5 ms/tick với 20 rắn, 1.5 ms/tick với khoảng 60 rắn (ngân sách là 40 ms/tick). Chưa đo trên NAS thật; CPU NAS (Celeron/Atom/Ryzen embedded) có thể chậm hơn vài lần nhưng vẫn còn dư.

## Giới hạn hiện tại

- Không lưu điểm/bảng xếp hạng lâu dài (restart là mất).
- Không có client-side prediction: con rắn của mình phản hồi trễ khoảng (RTT/2 + 110 ms). Với ping trong nước qua Cloudflare thì chơi vẫn mượt, nhưng ping cao sẽ thấy lái hơi "nặng".
- Một process Node.js, một phòng chơi duy nhất.
