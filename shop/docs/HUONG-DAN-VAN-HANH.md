# Hướng dẫn vận hành Kenvin Shop

Đăng nhập tại `https://<domain>/admin/`. Menu bên trái chỉ hiện các mục tài khoản được phép dùng.

## Việc cần làm trước khi mở bán

1. **Cấu hình cửa hàng**: kiểm tra tên shop, hotline, địa chỉ, giờ hoạt động, mạng xã hội. Nhập phí giao hàng, ngưỡng miễn phí ship, bật/tắt COD và chuyển khoản (nhập đủ thông tin ngân hàng). Bấm **Lưu**.
2. **Trang nội dung**: nhập nội dung Giới thiệu, Liên hệ, Chính sách giao hàng, Đổi trả, Bảo mật. Chuyển sang **Đã xuất bản**. Trang ở trạng thái Nháp thì khách không thấy.
3. **Danh mục, Thương hiệu, Thuộc tính** (ví dụ Dung tích, Màu sắc).
4. **Sản phẩm**: thêm từng sản phẩm, hoặc nhập bằng Excel.
5. **Trang chủ**: chọn sản phẩm nổi bật, đang giảm giá, hàng mới, danh mục nổi bật. **Banner**: thêm ảnh banner.

## Sản phẩm

- **Thêm sản phẩm**: nhập tên, chọn thương hiệu/danh mục, rồi nhập bảng giá:
  - Mỗi dòng là 1 biến thể (1 màu son, 1 dung tích). Sản phẩm 1 loại thì để 1 dòng, bỏ trống "Giá trị biến thể".
  - Giá nhập số, không dấu chấm. Ví dụ `159000`.
  - "Giá gốc" chỉ nhập khi đang giảm giá và phải lớn hơn giá bán. Khách sẽ thấy giá gạch ngang và % giảm.
  - Sửa tồn kho bắt buộc ghi lý do. Sửa giá nên ghi lý do. Mọi thay đổi đều được lưu lịch sử.
- **Trạng thái**: Nháp (chưa hiện) → Đang bán → Ẩn (ngừng bán). Bấm **Xem trước** để xem sản phẩm nháp như khách sẽ thấy.
- **Ảnh**: chọn nhiều ảnh cùng lúc. Dùng mũi tên để đổi thứ tự, dấu sao để chọn ảnh đại diện. Mỗi biến thể có thể chọn "Ảnh riêng" (ví dụ ảnh màu son).
- **Nội dung mô tả**: không nhập HTML.
  - Để 1 dòng trống giữa các đoạn.
  - `- ` đầu dòng để tạo gạch đầu dòng.
  - `## ` đầu dòng để tạo tiêu đề nhỏ.
  - `**chữ**` để in đậm.
  - Chỉ ghi công dụng/thành phần theo thông tin của nhà sản xuất.
- **Không xóa được** sản phẩm đã có trong đơn hàng. Hãy chuyển sang **Ẩn**.
- **Chọn nhiều sản phẩm** trong danh sách để đổi trạng thái hoặc đưa lên trang chủ hàng loạt.

## Giá và tồn kho

- **Tồn kho**: xem biến thể sắp hết/hết hàng; nút **Điều chỉnh** để nhập thêm, xuất bớt hoặc đặt lại theo kiểm kê.
- **Cập nhật giá hàng loạt**: chọn nhóm sản phẩm, chọn cách đổi giá → **Xem trước** → kiểm tra bảng → **Xác nhận**. Chưa xác nhận thì chưa đổi giá.
- Đơn đã đặt luôn giữ giá lúc khách mua, đổi giá sau đó không ảnh hưởng.

## Nhập/xuất Excel

1. Tải **file mẫu**, hoặc **xuất danh sách hiện tại** để sửa.
2. Mỗi dòng 1 biến thể. Các dòng cùng "Mã sản phẩm" là cùng 1 sản phẩm. Xem sheet "Hướng dẫn" trong file.
3. Tải file lên. Hệ thống báo lỗi theo từng dòng; có lỗi thì không ghi dòng nào.
4. Không lỗi thì xem trước, bấm **Xác nhận nhập dữ liệu**.
5. Cột "Tồn kho" là số lượng thực tế. Hệ thống tự tính chênh lệch và ghi lịch sử.

## Đơn hàng

Luồng xử lý: **Mới → Đã xác nhận → Đang đóng gói → Đang giao → Hoàn tất**.

- **Hủy đơn** (khi chưa giao): bắt buộc ghi lý do. Tồn kho tự cộng lại và lượt dùng mã giảm giá được trả lại.
- **Hoàn/trả hàng** (khi đang giao hoặc đã hoàn tất): tick "Đã nhận lại hàng" thì mới cộng lại tồn kho. Nếu chưa nhận lại hàng, sau này bấm **Đã nhận lại hàng — nhập lại kho**. Mỗi đơn chỉ hoàn kho được 1 lần.
- **Thanh toán** là mục riêng. Với chuyển khoản, chỉ bấm "Đã thanh toán" sau khi kiểm tra tài khoản ngân hàng đã nhận đúng số tiền, nội dung là mã đơn.
- Nhập **đơn vị vận chuyển và mã vận đơn**. **Ghi chú nội bộ** khách không nhìn thấy.
- **In** phiếu đóng gói hoặc phiếu giao hàng (1 đơn, hoặc chọn nhiều đơn trong danh sách). **Xuất Excel** theo bộ lọc đang chọn.
- Khách tra cứu đơn tại trang "Tra cứu đơn hàng" bằng mã đơn + số điện thoại.

## Mã giảm giá

- Giảm số tiền hoặc giảm %. Với loại %, có thể đặt mức giảm tối đa.
- Có thể đặt: thời gian bắt đầu/kết thúc, giá trị đơn tối thiểu, tổng số lượt, số lượt mỗi số điện thoại.
- Mỗi đơn chỉ dùng 1 mã. Mã không giảm phí ship.
- Mã đã có người dùng thì không xóa được, chỉ tắt được.

## Tài khoản và phân quyền

| Vai trò | Được làm |
|---|---|
| Chủ shop | Tất cả: doanh thu, khuyến mãi, cấu hình, tài khoản, nhật ký |
| Quản lý sản phẩm | Sản phẩm, danh mục, thương hiệu, giá, tồn kho, Excel |
| Xử lý đơn hàng | Xem/xử lý đơn, vận đơn, thanh toán. Không sửa giá |
| Nội dung | Banner, trang nội dung, nội dung trang chủ |

- Một người có thể có nhiều vai trò. Nhân viên nghỉ việc: bỏ tick "Đang hoạt động" để khóa tài khoản.
- Hệ thống luôn giữ ít nhất 1 tài khoản Chủ shop đang hoạt động.
- **Nhật ký thao tác** ghi lại đăng nhập, sửa sản phẩm, đổi giá, xử lý đơn, đổi cấu hình...

## Dashboard

- Số đơn mới, cần xử lý, đang giao.
- Doanh thu = tổng tiền các đơn **Hoàn tất** trong khoảng thời gian đã chọn, tính theo ngày hoàn tất.
- Danh sách sản phẩm sắp hết hàng. Đổi ngưỡng cảnh báo trong Cấu hình.
