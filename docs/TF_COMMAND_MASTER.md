# TF Command Master

Tài liệu quản lý command toàn hệ thống TF Bot. Danh sách này được lập từ các `CommandHandler` hiện có trong `main.py`.

Ghi chú tổng quan:

- `docs/BOTFATHER_COMMANDS.txt` là file dùng để copy trực tiếp vào BotFather -> Edit Commands.
- Không thêm dấu `/` vào command trong file BotFather.
- `main.py` hiện có 97 dòng đăng ký `CommandHandler`, tương ứng 96 command unique.
- `payrollweek` đang được đăng ký 2 lần trong `main.py`; tài liệu chỉ liệt kê 1 lần để tránh trùng khi cấu hình BotFather.

## Hệ thống & Cá nhân

| Module | Command | Chức năng | Vai trò sử dụng | Ghi chú |
| --- | --- | --- | --- | --- |
| Hệ thống | `start` | Khởi động bot và xem danh sách lệnh | Tất cả người dùng | Hiển thị help tổng quan |
| Hệ thống | `getchatid` | Xem Telegram chat ID hiện tại | Quản trị / vận hành | Dùng khi cấu hình nhóm |
| Hệ thống | `linkshiftgroup` | Liên kết nhóm hiện tại với nhóm xếp ca | Quản trị / Mr.Win | Dùng cho nhóm cần lấy lịch từ nhóm khác |
| Hệ thống | `help` | Xem hướng dẫn sử dụng bot | Tất cả người dùng | Gọi lại nội dung `/start` |
| Cá nhân / lịch nhắc | `addat` | Thêm lịch nhắc vận hành theo giờ | Quản trị / vận hành | Lệnh nhắc lịch chung |
| Cá nhân / lịch nhắc | `list` | Xem danh sách lịch nhắc | Tất cả người dùng | Áp dụng trong từng chat |
| Cá nhân / lịch nhắc | `remove` | Xóa một lịch nhắc | Quản trị / vận hành | Xóa theo số thứ tự |
| Cá nhân / lịch nhắc | `clear` | Xóa toàn bộ lịch nhắc | Quản trị / vận hành | Áp dụng trong chat hiện tại |
| Cá nhân / lịch nhắc | `now` | Xem lịch nhắc hiện tại | Tất cả người dùng | Kiểm tra nhanh lịch nhắc |
| Cá nhân / lịch nhắc | `report` | Xem báo cáo vận hành hôm nay | Quản lý / vận hành | Tổng hợp các mục DONE |
| Cá nhân / lịch nhắc | `addmonthly` | Thêm lịch nhắc hằng tháng | Quản trị / vận hành | Lịch theo ngày dương |
| Cá nhân / lịch nhắc | `monthlylist` | Xem lịch nhắc hằng tháng | Tất cả người dùng | Lịch theo tháng |
| Cá nhân / lịch nhắc | `removemonthly` | Xóa lịch nhắc hằng tháng | Quản trị / vận hành | Xóa theo số thứ tự |
| Cá nhân / lịch nhắc | `addlunar` | Thêm lịch nhắc âm lịch | Quản trị / vận hành | Lịch âm |
| Cá nhân / lịch nhắc | `lunarlist` | Xem lịch nhắc âm lịch | Tất cả người dùng | Lịch âm |
| Cá nhân / lịch nhắc | `removelunar` | Xóa lịch nhắc âm lịch | Quản trị / vận hành | Xóa theo số thứ tự |
| Cá nhân / lịch nhắc | `addbirthday` | Thêm lịch nhắc sinh nhật | Quản trị / vận hành | Lịch sinh nhật |
| Cá nhân / lịch nhắc | `birthdaylist` | Xem lịch nhắc sinh nhật | Tất cả người dùng | Lịch sinh nhật |
| Cá nhân / lịch nhắc | `removebirthday` | Xóa lịch nhắc sinh nhật | Quản trị / vận hành | Xóa theo số thứ tự |

## Chấm công & Tính lương

| Module | Command | Chức năng | Vai trò sử dụng | Ghi chú |
| --- | --- | --- | --- | --- |
| Chấm công & Tính lương | `todaywork` | Xem công việc và ca hôm nay | Nhân viên / quản lý | Kiểm tra công việc trong ngày |
| Chấm công & Tính lương | `checkin` | Chấm công vào ca | Nhân viên | Ghi vào dữ liệu chấm công |
| Chấm công & Tính lương | `checkout` | Chấm công ra ca | Nhân viên | Tính thời lượng làm việc |
| Chấm công & Tính lương | `timesheet` | Xem bảng chấm công | Mr.Win / Sếp Tiến | Xem dữ liệu chấm công |
| Chấm công & Tính lương | `payrollweek` | Xem bảng lương tuần | Mr.Win / Sếp Tiến | Đang đăng ký 2 lần trong `main.py` |
| Chấm công & Tính lương | `payrollmonth` | Xem bảng lương tháng | Mr.Win / Sếp Tiến | Báo cáo tháng |
| Chấm công & Tính lương | `payrollfinal` | Chốt lương cuối kỳ | Mr.Win / Sếp Tiến | Chốt bảng lương |
| Chấm công & Tính lương | `payrolllock` | Khóa bảng lương | Mr.Win / Sếp Tiến | Chống sửa khi đã khóa |
| Chấm công & Tính lương | `payrollunlock` | Mở khóa bảng lương | Mr.Win / Sếp Tiến | Mở lại bảng lương |
| Chấm công & Tính lương | `payslip` | Xem phiếu lương nhân viên | Nhân viên / Mr.Win | Phiếu lương cá nhân |
| Chấm công & Tính lương | `clearattendance` | Xóa dữ liệu chấm công | Quản trị / Mr.Win | Dùng cẩn trọng |
| Chấm công & Tính lương | `salarytype` | Cấu hình loại lương nhân viên | Mr.Win / Sếp Tiến | Cấu hình lương |
| Chấm công & Tính lương | `sethourly` | Cấu hình lương theo giờ | Mr.Win / Sếp Tiến | Cấu hình lương giờ |
| Chấm công & Tính lương | `fixedsalary` | Cấu hình lương cố định | Mr.Win / Sếp Tiến | Cấu hình lương tháng |
| Chấm công & Tính lương | `bonus` | Thêm thưởng nhân viên | Mr.Win / Sếp Tiến | Khoản cộng lương |
| Chấm công & Tính lương | `bonusremove` | Xóa thưởng nhân viên | Mr.Win / Sếp Tiến | Điều chỉnh thưởng |
| Chấm công & Tính lương | `advance` | Ghi nhận ứng lương | Mr.Win / Sếp Tiến | Khoản trừ lương |
| Chấm công & Tính lương | `fine` | Thêm khoản phạt | Mr.Win / Sếp Tiến | Khoản trừ lương |
| Chấm công & Tính lương | `fineremove` | Xóa khoản phạt | Mr.Win / Sếp Tiến | Điều chỉnh phạt |
| Chấm công & Tính lương | `finelist` | Xem danh sách khoản phạt | Mr.Win / Sếp Tiến | Theo dõi phạt |
| Chấm công & Tính lương | `resetpayroll` | Reset dữ liệu lương | Mr.Win / Sếp Tiến | Dùng cẩn trọng |
| Chấm công & Tính lương | `salarylist` | Xem danh sách cấu hình lương | Mr.Win / Sếp Tiến | Danh sách lương |
| Chấm công & Tính lương | `payrollsummary` | Tổng hợp bảng lương | Mr.Win / Sếp Tiến | Tổng hợp chi trả |
| Chấm công & Tính lương | `payrollexport` | Xuất dữ liệu bảng lương | Mr.Win / Sếp Tiến | Xuất sang sheet |
| Chấm công & Tính lương | `fixcheckin` | Sửa giờ checkin | Mr.Win / Sếp Tiến | Sửa dữ liệu chấm công |
| Chấm công & Tính lương | `fixcheckout` | Sửa giờ checkout | Mr.Win / Sếp Tiến | Sửa dữ liệu chấm công |
| Chấm công & Tính lương | `staffadd` | Thêm nhân viên | Mr.Win / Sếp Tiến | Quản lý nhân sự |
| Chấm công & Tính lương | `staffremove` | Xóa nhân viên | Mr.Win / Sếp Tiến | Quản lý nhân sự |
| Chấm công & Tính lương | `stafflist` | Xem danh sách nhân viên | Quản lý / vận hành | Danh sách active/inactive |

## Xếp ca

| Module | Command | Chức năng | Vai trò sử dụng | Ghi chú |
| --- | --- | --- | --- | --- |
| Xếp ca | `checkshift` | Kiểm tra lệch lịch ca và chấm công | Mr.Win / Sếp Tiến | Đối chiếu lịch và chấm công |
| Xếp ca | `shift` | Xếp ca nhanh | Nhân viên / Mr.Win | Xếp ca đơn giản |
| Xếp ca | `week` | Xem tuần làm việc | Nhân viên / quản lý | Theo tuần |
| Xếp ca | `ranh` | Đăng ký lịch rảnh | Nhân viên | Đầu vào xếp ca |
| Xếp ca | `checkranh` | Xem lịch rảnh | Mr.Win / Sếp Tiến | Kiểm tra lịch rảnh |
| Xếp ca | `xepca` | Xếp ca tuần | Mr.Win / Sếp Tiến | Ghi lịch tuần |
| Xếp ca | `lich` | Xem lịch làm việc | Nhân viên / quản lý | Lịch tuần |
| Xếp ca | `xoaca` | Xóa ca làm | Mr.Win / Sếp Tiến | Điều chỉnh lịch |
| Xếp ca | `tonggio` | Tổng hợp giờ làm | Mr.Win / Sếp Tiến | Theo lịch/chấm công |
| Xếp ca | `thieuca` | Xem ca còn thiếu người | Mr.Win / Sếp Tiến | Kiểm tra thiếu nhân sự |
| Xếp ca | `doica` | Đổi ca làm | Nhân viên / Mr.Win | Đổi ca |
| Xếp ca | `duyetca` | Duyệt ca làm | Mr.Win / Sếp Tiến | Duyệt đổi/xếp ca |
| Xếp ca | `scanthieuca` | Quét ca thiếu người | Mr.Win / Sếp Tiến | Kiểm tra tự động |
| Xếp ca | `chotlich` | Chốt lịch làm việc | Mr.Win / Sếp Tiến | Chốt lịch tuần |
| Xếp ca | `canhan` | Xem lịch cá nhân | Nhân viên | Lịch của từng người |
| Xếp ca | `nhanvien` | Xem danh sách nhân viên xếp ca | Mr.Win / Sếp Tiến | Nguồn nhân sự |
| Xếp ca | `canhdong` | Báo cáo cân đồng | Mr.Win / Sếp Tiến | Báo cáo đặc thù vận hành |
| Xếp ca | `clearshift` | Xóa lịch ca | Mr.Win / Sếp Tiến | Dùng cẩn trọng |

## Kho & Nhập hàng

| Module | Command | Chức năng | Vai trò sử dụng | Ghi chú |
| --- | --- | --- | --- | --- |
| Kho & Nhập hàng | `tonkho` | Xem tồn kho | Nhân viên / Mr.Happy | Tổng quan kho |
| Kho & Nhập hàng | `khohelp` | Xem hướng dẫn module kho | Nhân viên / Mr.Happy | Help riêng cho kho |
| Kho & Nhập hàng | `nhaphang` | Gửi mẫu nhập hàng | Mr.Happy / Sếp Tiến | Mẫu nhập hàng |
| Kho & Nhập hàng | `thieuhang` | Gửi mẫu báo thiếu hàng | Nhân viên / Mr.Happy | Mẫu báo thiếu |
| Kho & Nhập hàng | `xuatkho` | Gửi mẫu xuất kho | Mr.Happy / Sếp Tiến | Mẫu xuất kho |
| Kho & Nhập hàng | `kiemkho` | Gửi mẫu kiểm kho | Mr.Happy / Sếp Tiến | Mẫu kiểm kho |
| Kho & Nhập hàng | `baocaokho` | Gửi mẫu báo cáo kho ngày | Mr.Happy / Sếp Tiến | Mẫu báo cáo ngày |
| Kho & Nhập hàng | `baocaokhotuan` | Gửi mẫu báo cáo kho tuần | Mr.Happy / Sếp Tiến | Mẫu báo cáo tuần |

## Doanh thu & P/L

| Module | Command | Chức năng | Vai trò sử dụng | Ghi chú |
| --- | --- | --- | --- | --- |
| Doanh thu & P/L | `revenue` | Ghi nhận doanh thu | Mr.Happy / Sếp Tiến | Doanh thu ngày |
| Doanh thu & P/L | `revenuelist` | Xem danh sách doanh thu | Mr.Happy / Sếp Tiến | Danh sách giao dịch |
| Doanh thu & P/L | `revenueweek` | Báo cáo doanh thu tuần | Mr.Happy / Sếp Tiến | Tổng hợp tuần |
| Doanh thu & P/L | `revenuemonth` | Báo cáo doanh thu tháng | Mr.Happy / Sếp Tiến | Tổng hợp tháng |
| Doanh thu & P/L | `revenuedashboard` | Xem dashboard doanh thu | Mr.Happy / Sếp Tiến | Dashboard nhanh |
| Doanh thu & P/L | `income` | Ghi nhận khoản thu | Mr.Happy / Sếp Tiến | Alias nhóm thu |
| Doanh thu & P/L | `expense` | Ghi nhận chi phí | Mr.Happy / Sếp Tiến | Chi phí |
| Doanh thu & P/L | `thu` | Xem danh sách khoản thu | Mr.Happy / Sếp Tiến | Alias danh sách thu |
| Doanh thu & P/L | `expenselist` | Xem danh sách chi phí | Mr.Happy / Sếp Tiến | Danh sách chi |
| Doanh thu & P/L | `pl` | Xem báo cáo P/L | Mr.Happy / Sếp Tiến | Lãi/lỗ |
| Doanh thu & P/L | `financeweek` | Xem báo cáo tài chính tuần | Mr.Happy / Sếp Tiến | Tổng hợp tuần |
| Doanh thu & P/L | `financemonth` | Xem báo cáo tài chính tháng | Mr.Happy / Sếp Tiến | Tổng hợp tháng |
| Doanh thu & P/L | `resetfinance` | Reset dữ liệu tài chính | Mr.Happy / Sếp Tiến | Dùng cẩn trọng |
| Doanh thu & P/L | `plmonth` | Xem báo cáo P/L tháng | Mr.Happy / Sếp Tiến | Báo cáo tháng |

## Đề nghị thanh toán

| Module | Command | Chức năng | Vai trò sử dụng | Ghi chú |
| --- | --- | --- | --- | --- |
| Đề nghị thanh toán | `paymentrequest` | Tạo đề nghị thanh toán | Nhân viên / Mr.Happy / Mr.Win / Miss Uyên | Ghi Google Sheet `12_De_Nghi_Thanh_Toan` |
| Đề nghị thanh toán | `paymentlist` | Xem danh sách đề nghị thanh toán | Nhân viên / quản lý | Danh sách gần nhất |
| Đề nghị thanh toán | `paymentdetail` | Xem chi tiết đề nghị thanh toán | Nhân viên / quản lý | Tra theo ID |
| Đề nghị thanh toán | `paymentpending` | Xem đề nghị đang chờ duyệt | Miss Uyên / Sếp Tiến | Trạng thái `CHO_DUYET` |
| Đề nghị thanh toán | `paymentapprove` | Duyệt đề nghị thanh toán | Miss Uyên | Chuyển sang `DA_DUYET` |
| Đề nghị thanh toán | `paymentreject` | Từ chối đề nghị thanh toán | Miss Uyên | Ghi lý do vào ghi chú |
| Đề nghị thanh toán | `paymentpaid` | Xác nhận đã thanh toán | Miss Uyên | Chuyển sang `DA_THANH_TOAN` |
| Đề nghị thanh toán | `paymentreport` | Báo cáo đề nghị thanh toán | Sếp Tiến | Theo tuần hoặc tháng |
