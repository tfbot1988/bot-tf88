# Bot TF PRO

Telegram bot nhắc việc chạy bằng Python.

## Biến môi trường cần có
- `BOT_TOKEN`: token bot Telegram từ BotFather
- `TZ`: `Asia/Ho_Chi_Minh` (không bắt buộc, mặc định đã là giờ Việt Nam)

## Lệnh bot
- `/start`
- `/addat <giờ> <ngày> <nội dung>`
- `/list`
- `/remove <số>`
- `/clear`
- `/now`
- `/paymentrequest LOAI_CHI_PHI SO_TIEN NOI_DUNG`
- `/paymentlist`
- `/paymentdetail ID`
- `/paymentpending`
- `/paymentapprove ID`
- `/paymentreject ID`
- `/paymentpaid ID`
- `/paymentreport week|month`

Ví dụ:
```
/addat 06:38 tue,wed,thu,fri,sat MỞ CA SÁNG TF
/addat 21:38 mon,tue,wed,thu,fri,sat ĐÓNG CA TF
/paymentrequest KHO 1500000 Nhập hàng sữa
```

## Render
Chạy bằng Background Worker hoặc Web Service paid.
Start command:
```
python main.py
```
