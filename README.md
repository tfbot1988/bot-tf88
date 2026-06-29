# TF COMMAND MASTER LIST - PROJECT SUMMARY

Telegram Bot quản lý vận hành TF Coffee.

## Module đang có

- Chấm công & Tính lương
- Xếp ca
- Kho & Nhập hàng
- Doanh thu & P/L
- Đề nghị thanh toán
- Nhắc lịch vận hành

## Command Master List

### Chấm công & Tính lương

- `/todaywork`
- `/checkin Tên`
- `/checkout Tên`
- `/fixcheckin Tên HH:MM`
- `/fixcheckout Tên HH:MM`
- `/payrollweek`
- `/payrollmonth`
- `/salarylist`
- `/payrollexport`
- `/resetpayroll`
- `/staffadd Tên`
- `/stafflist`
- `/staffremove Tên`
- `/salarytype Tên Loại`
- `/fixedsalary Tên Số_tiền`

### Xếp ca

- `/shift`
- `/week`
- `/ranh`
- `/lich`
- `/tonggio`
- `/thieuca`
- `/nhanvien`
- `/canhan`
- `/canhdong`
- `/clearshift`
- `/chotlich`
- `/doica`
- `/duyetca`
- `/scanthieuca`

### Kho & Nhập hàng

- `/tonkho`
- `/nhaphang`
- `/xuatkho`
- `/thieuhang`
- `/kiemkho`
- `/khohelp`

### Doanh thu & P/L

- `/revenue`
- `/revenuelist`
- `/revenueweek`
- `/revenuemonth`
- `/revenuedashboard`
- `/expense`
- `/expenselist`
- `/pl`
- `/financeweek`
- `/financemonth`
- `/resetfinance`

### Đề nghị thanh toán

- `/paymentrequest LOAI_CHI_PHI SO_TIEN NOI_DUNG`
- `/paymentlist`
- `/paymentdetail ID`
- `/paymentpending`
- `/paymentapprove ID`
- `/paymentreject ID Lý_do`
- `/paymentpaid ID`
- `/paymentreport week`
- `/paymentreport month`

### Nhắc lịch vận hành

- `/start`
- `/help`
- `/addat <giờ> <ngày> <nội dung>`
- `/list`
- `/remove <số>`
- `/clear`
- `/now`
- `/report`

## Phân quyền định hướng

- Nhân viên: command hằng ngày như `/checkin`, `/checkout`, `/todaywork`, `/shift`, `/lich`, `/tonkho`, `/paymentrequest`, `/paymentlist`, `/paymentdetail`.
- Mr.Win: nhóm chấm công, tính lương và xếp ca nâng cao.
- Mr.Happy: nhóm doanh thu, P/L, kho, nhập hàng và xuất kho.
- Miss Uyên: duyệt, từ chối và xác nhận thanh toán đề nghị.
- Sếp Tiến: toàn quyền và xem báo cáo.

Khuyến nghị cấu hình quyền bằng Telegram User ID.

## Google Sheet chính

- `12_De_Nghi_Thanh_Toan`: source of truth cho module đề nghị thanh toán.

Header:

| Cột | Tên |
| --- | --- |
| A | Mã đề nghị |
| B | Ngày đề nghị |
| C | Người đề nghị |
| D | Loại chi phí |
| E | Nội dung |
| F | Số tiền |
| G | Trạng thái |
| H | Người duyệt |
| I | Ngày duyệt |
| J | Người thanh toán |
| K | Ngày thanh toán |
| L | Ghi chú |

Trạng thái:

- `CHO_DUYET`
- `DA_DUYET`
- `TU_CHOI`
- `DA_THANH_TOAN`

## Biến môi trường cần có

- `BOT_TOKEN`: token bot Telegram từ BotFather
- `TZ`: mặc định `Asia/Ho_Chi_Minh`
- `GOOGLE_CREDENTIALS`: service account JSON cho Google Sheet
- `PAYMENT_CREATOR_USER_IDS`: danh sách Telegram User ID được tạo đề nghị, phân tách bằng dấu phẩy
- `PAYMENT_APPROVER_USER_IDS`: Telegram User ID của Miss Uyên
- `PAYMENT_BOSS_USER_IDS`: Telegram User ID của Sếp Tiến

## Ví dụ test nhanh

```text
/paymentrequest KHO 1500000 Nhập hàng sữa
/paymentlist
/paymentdetail DN001
/paymentpending
/paymentapprove DN001
/paymentreject DN002 Thiếu hóa đơn
/paymentpaid DN001
/paymentreport week
/paymentreport month
```

## Render

Chạy bằng Background Worker hoặc Web Service paid.

Start command:

```bash
python main.py
```
