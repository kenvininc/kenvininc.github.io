# Kenvin Shop

Website bán mỹ phẩm: cửa hàng cho khách và control panel `/admin/` cho người quản trị.

- Backend: Django 5.2 LTS (hỗ trợ đến 04/2028), Python 3.12
- Database: PostgreSQL 16
- Chạy bằng Docker Compose: `db` (PostgreSQL), `web` (gunicorn), `nginx` (phục vụ ảnh/static, proxy vào app)
- Giao diện render ở server, CSS/JS tự viết, không dùng CDN, analytics hay dịch vụ bên thứ ba

Tài liệu:
- [DEPLOY.md](DEPLOY.md): triển khai lên Synology, publish domain, backup/restore, cập nhật phiên bản
- [docs/HUONG-DAN-VAN-HANH.md](docs/HUONG-DAN-VAN-HANH.md): hướng dẫn ngắn cho người vận hành
- [docs/mau-nhap-san-pham.xlsx](docs/mau-nhap-san-pham.xlsx): file Excel mẫu nhập sản phẩm

## Cấu trúc

```
apps/core        cấu hình shop, phân quyền, nhật ký, xử lý ảnh, định dạng nội dung
apps/catalog     danh mục, thương hiệu, sản phẩm, biến thể, lịch sử giá/tồn kho, Excel
apps/promotions  mã giảm giá
apps/orders      giỏ hàng, tính tiền, đặt hàng, xử lý đơn
apps/content     banner, trang nội dung
apps/storefront  giao diện khách
apps/panel       control panel /admin/
deploy/          entrypoint container, cấu hình nginx
scripts/         backup.sh, restore.sh
tests/           test tự động
```

## Quy tắc nghiệp vụ đã cài đặt

**Giá và tiền**
- Tiền lưu dạng số nguyên đồng (`BigInteger`), không dùng số thực.
- Giá, tồn kho, mã giảm giá, phí ship và tổng tiền đều tính lại ở server khi đặt hàng. Giá trị do trình duyệt gửi lên bị bỏ qua.
- Đơn lưu bản chụp tên sản phẩm, phân loại, SKU, đơn giá, giá gốc và ảnh tại thời điểm đặt. Sửa sản phẩm sau đó không làm thay đổi đơn cũ.
- Database có ràng buộc `tổng = tiền hàng − giảm giá + phí ship`.

**Tồn kho**
- Tồn kho bị trừ ngay khi tạo đơn, trong cùng transaction, có khóa dòng biến thể (`SELECT … FOR UPDATE`). Không đủ hàng thì không tạo đơn, nên không bán vượt tồn.
- Hủy đơn (khi đang ở Mới, Đã xác nhận hoặc Đang đóng gói): hoàn tồn đúng 1 lần.
- Hoàn/trả hàng: chỉ hoàn tồn khi admin xác nhận đã nhận lại hàng, và chỉ 1 lần.
- Database có ràng buộc `stock >= 0`. Mỗi dòng đơn chỉ được trừ kho 1 lần và hoàn kho 1 lần (unique constraint).
- Mọi thay đổi tồn đều ghi lịch sử: ai làm, lúc nào, chênh lệch, tồn sau thay đổi, lý do.
- Khi admin sửa tồn hoặc giá mà dữ liệu đã bị thay đổi kể từ lúc mở form (ví dụ có đơn mới chen vào), hệ thống báo lỗi chứ không ghi đè.

**Chống tạo đơn trùng**
- Form đặt hàng mang `idempotency_key` (UUID, unique trong database). Khi khách bấm liên tục, gửi lại request hoặc 2 request đến cùng lúc, chỉ có 1 đơn được tạo và kho chỉ bị trừ 1 lần.

**Mã giảm giá**
- Mỗi đơn dùng tối đa 1 mã. Mã giảm theo số tiền hoặc theo %, có thể đặt mức giảm tối đa.
- Mã tính trên tiền hàng (giá bán đã gồm khuyến mãi của sản phẩm), không giảm phí giao hàng. Số tiền giảm không vượt quá tiền hàng.
- Điều kiện được kiểm tra ở backend: thời gian hiệu lực, giá trị đơn tối thiểu, tổng lượt dùng, lượt dùng theo số điện thoại.
- Khi hủy đơn, lượt dùng mã được trả lại.

**Phí giao hàng**
- Đồng giá. Miễn phí khi tiền hàng sau giảm giá đạt ngưỡng (nếu có cấu hình). Chủ shop nhập trong Cấu hình cửa hàng.

**Thanh toán**
- COD và chuyển khoản ngân hàng, bật/tắt trong Cấu hình.
- Chưa tích hợp cổng thanh toán online. Đơn chuyển khoản chỉ được đánh dấu "Đã thanh toán" khi admin tự đối chiếu tài khoản. Hệ thống không bao giờ tự đánh dấu đã thanh toán.
- Trạng thái xử lý đơn và trạng thái thanh toán là 2 trường độc lập.

**Doanh thu ở dashboard**
- Tổng "Tổng thanh toán" của các đơn ở trạng thái Hoàn tất, tính theo ngày chuyển sang Hoàn tất. Không trừ giá vốn.

**Email**
- Tùy chọn qua SMTP. Email được gửi sau khi đơn đã lưu. Gửi lỗi chỉ ghi log và lịch sử đơn, không làm mất đơn.

## Bảo mật

- Mật khẩu hash bằng Argon2. Không có tài khoản hay mật khẩu mặc định; tài khoản đầu tiên tạo bằng lệnh `create_owner`.
- Đăng nhập admin: sai 5 lần/15 phút theo tên đăng nhập, hoặc 20 lần/15 phút theo IP, thì bị chặn tạm. Session admin hết hạn sau 8 giờ.
- Mỗi view của panel đều kiểm tra quyền ở backend, cả GET lẫn POST.
- Cookie `HttpOnly`, `SameSite=Lax`, `Secure` khi chạy HTTPS. Có CSRF cho mọi form POST. Có Content-Security-Policy và `X-Frame-Options: DENY`.
- Truy vấn qua ORM, không ghép SQL thủ công. Nội dung admin nhập bị escape; định dạng chỉ hỗ trợ cú pháp giới hạn (không HTML).
- Ảnh upload: kiểm tra bằng nội dung file (Pillow), chỉ nhận JPEG/PNG/WEBP, giới hạn dung lượng và số pixel. Ảnh được mã hóa lại thành WEBP với tên ngẫu nhiên (bỏ metadata). Nginx chỉ phục vụ file ảnh trong `/media/`.
- File Excel xuất ra chặn công thức (formula injection).
- Log không ghi mật khẩu/token. Nhật ký đăng nhập sai chỉ ghi tên đăng nhập.
- Khách tra cứu đơn bằng mã đơn + số điện thoại, có giới hạn số lần thử.

## Chạy local (phát triển)

Cần Python 3.12+ và PostgreSQL 14+.

```bash
cd shop
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export DEBUG=1 POSTGRES_HOST=127.0.0.1 POSTGRES_DB=kenvinshop POSTGRES_USER=... POSTGRES_PASSWORD=... SECURE_COOKIES=0
python manage.py migrate
python manage.py createcachetable
python manage.py create_owner --username tenban
python manage.py seed_demo        # tùy chọn: dữ liệu DEMO, chỉ chạy được khi DEBUG=1
python manage.py runserver
```

Xóa dữ liệu demo: `python manage.py seed_demo --clear`

Hoặc chạy cả stack bằng Docker: xem DEPLOY.md.

## Test

```bash
python manage.py test tests
```

Test cần PostgreSQL. Test đặt hàng đồng thời sẽ tự bỏ qua nếu không có PostgreSQL.

## Trạng thái

### Đã làm và đã kiểm tra

Test tự động: 40 test, chạy pass trên PostgreSQL 16 ngày 16/10/2026.
- Tính giá, mã giảm giá (cố định, %, mức tối đa, điều kiện, giới hạn theo số điện thoại), phí ship, định dạng VND
- Đặt hàng: lưu bản chụp, đúng tổng tiền, trừ kho, không bán vượt tồn, gửi lặp không tạo đơn trùng, chặn sản phẩm ẩn
- Đặt hàng đồng thời: 8 request tranh 3 sản phẩm cuối → chỉ 3 đơn thành công. 5 request cùng `idempotency_key` → chỉ 1 đơn
- Hủy đơn, hoàn hàng: hoàn kho đúng 1 lần, trả lượt mã giảm giá. Chặn chuyển trạng thái sai luồng
- Lỗi gửi email không làm mất đơn
- Phân quyền: tài khoản thiếu quyền gọi trực tiếp URL/POST đều bị 403. Chặn dò mật khẩu. Không xóa được Chủ shop cuối cùng
- Admin tạo sản phẩm có biến thể + ảnh → khách tìm kiếm (không dấu), thêm giỏ, đặt hàng → admin xử lý đơn, vận đơn, ghi chú
- Sửa giá sau khi đặt không làm đổi đơn cũ. Có lịch sử giá
- Sửa tồn kho bắt buộc nhập lý do. Phát hiện khi có thay đổi chen vào giữa lúc mở form và lúc lưu
- Từ chối file giả ảnh (PHP, SVG)
- Cập nhật giá hàng loạt: xem trước, rồi xác nhận
- Nhập Excel báo lỗi theo dòng. File hợp lệ chỉ ghi sau khi xác nhận. Nhập lại có ghi lịch sử giá/tồn. Xuất Excel chặn công thức

Kiểm tra thủ công trong môi trường phát triển:
- Giao diện bằng Chromium (Playwright) ở desktop 1366px, iPhone 13 và tablet 820px: trang chủ, mega menu, danh mục, bộ lọc trên điện thoại, chi tiết sản phẩm, giỏ, đặt hàng, admin
- Stack Docker Compose: build image, admin tạo sản phẩm + upload ảnh, khách đặt hàng, `docker compose down` rồi `up` lại → đơn, tồn kho và ảnh vẫn còn
- `scripts/backup.sh` và `scripts/restore.sh`: xóa đơn và ảnh, rồi khôi phục lại được

### Chưa làm / cần chủ shop xác nhận

- **Chưa triển khai lên NAS.** Chưa kiểm tra trên Synology thật: CPU/kiến trúc của NAS ảo, RAM, port 8687 còn trống không, quyền thư mục.
- Domain cho shop: chưa có.
- Phí giao hàng, phương thức thanh toán, thông tin ngân hàng, đơn vị vận chuyển: chưa xác nhận. Đã làm sẵn cấu hình trong admin, mặc định chỉ bật COD và phí ship 0đ.
- Nội dung các trang chính sách (giao hàng, đổi trả, bảo mật, giới thiệu): đang để Nháp và trống, chủ shop cần tự nhập.
- Logo và màu chủ đạo: đang dùng logo chữ và màu #B23A62. Đổi được trong admin.
- Vai trò nhân viên: đang dùng 4 vai trò đề xuất (Chủ shop, Quản lý sản phẩm, Xử lý đơn hàng, Nội dung), chưa được chủ shop xác nhận.
- Không có: cổng thanh toán online, API đơn vị vận chuyển, tài khoản khách hàng, đánh giá sản phẩm, tính phí ship theo tỉnh/khối lượng, nhiều mã giảm giá trên một đơn, biến thể nhiều chiều (ví dụ vừa màu vừa dung tích), soạn thảo nội dung dạng WYSIWYG, nhập ảnh qua Excel.
- Email: đã có chức năng nhưng chưa cấu hình SMTP, chưa test gửi thật.
- Chưa test tải (load test). Chưa test trên Safari/iOS thật, chỉ mới giả lập iPhone trên Chromium.
