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

Ví dụ:
```
/addat 06:38 tue,wed,thu,fri,sat MỞ CA SÁNG TF
/addat 21:38 mon,tue,wed,thu,fri,sat ĐÓNG CA TF
```

## Render
Chạy bằng Background Worker hoặc Web Service paid.
Start command:
```
python main.py
```
