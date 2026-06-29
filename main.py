import os
import json
import logging
from pathlib import Path
from datetime import datetime, time, timedelta
from turtle import update
from unittest import result
from zoneinfo import ZoneInfo
from gspread import spreadsheet
from lunardate import LunarDate
from typing import Dict, List, Any, Optional
import gspread
from google.oauth2.service_account import Credentials

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("tf-bot-pro")

TOKEN = os.getenv("BOT_TOKEN")
TZ_NAME = os.getenv("TZ", "Asia/Ho_Chi_Minh")
TZ = ZoneInfo(TZ_NAME)
DATA_FILE = Path(os.getenv("DATA_FILE", "/app/data/data.json"))
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
gs_client = None

if GOOGLE_CREDENTIALS:
    creds = Credentials.from_service_account_info(
        json.loads(GOOGLE_CREDENTIALS),
        scopes=SCOPES
    )
    gs_client = gspread.authorize(creds)
DAY_MAP = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

DAY_LABEL = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def load_data() -> Dict[str, Any]:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            log.exception("Failed to read data file; starting empty.")
    return {"chats": {}}

def save_data(data: Dict[str, Any]) -> None:
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

DATA = load_data()
PAYROLL_LOCK = {}
DATA.setdefault("salary", {})
DATA.setdefault("fifo_stock", {})
DATA.setdefault("revenue", {})
DATA.setdefault("expense", {})
SHEET_URL = "https://docs.google.com/spreadsheets/d/1-2CUwuORi7L4HIUMx7n7uUVhMIFXL0_95PVp3_LGGe8/edit"

def get_worksheet(sheet_name):
    if not gs_client:
        print("NO GS CLIENT")
        return None

    print("OPEN SHEET URL:", SHEET_URL)
    print("REQUEST SHEET:", sheet_name)

    spreadsheet = gs_client.open("TF - Hệ Thống Vận Hành")

    print("SHEET TITLES:", [ws.title for ws in spreadsheet.worksheets()])

    return spreadsheet.worksheet(sheet_name)

PAYMENT_SHEET_NAME = "12_De_Nghi_Thanh_Toan"
PAYMENT_HEADERS = [
    "Mã đề nghị",
    "Ngày đề nghị",
    "Người đề nghị",
    "Loại chi phí",
    "Nội dung",
    "Số tiền",
    "Trạng thái",
    "Người duyệt",
    "Ngày duyệt",
    "Người thanh toán",
    "Ngày thanh toán",
    "Ghi chú",
]
PAYMENT_STATUS_PENDING = "CHO_DUYET"
PAYMENT_STATUS_APPROVED = "DA_DUYET"
PAYMENT_STATUS_REJECTED = "TU_CHOI"
PAYMENT_STATUS_PAID = "DA_THANH_TOAN"
PAYMENT_APPROVER_USER_IDS = {
    user_id.strip()
    for user_id in os.getenv("PAYMENT_APPROVER_USER_IDS", "").split(",")
    if user_id.strip()
}
PAYMENT_APPROVER_USERNAMES = {
    username.strip().lower().lstrip("@")
    for username in os.getenv("PAYMENT_APPROVER_USERNAMES", "").split(",")
    if username.strip()
}
PAYMENT_APPROVER_FULL_NAMES = {
    name.strip().lower()
    for name in os.getenv("PAYMENT_APPROVER_FULL_NAMES", "").split(",")
    if name.strip()
}
PAYMENT_CREATOR_USER_IDS = {
    user_id.strip()
    for user_id in os.getenv("PAYMENT_CREATOR_USER_IDS", "").split(",")
    if user_id.strip()
}
PAYMENT_CREATOR_USERNAMES = {
    username.strip().lower().lstrip("@")
    for username in os.getenv("PAYMENT_CREATOR_USERNAMES", "").split(",")
    if username.strip()
}
PAYMENT_CREATOR_FULL_NAMES = {
    name.strip().lower()
    for name in os.getenv("PAYMENT_CREATOR_FULL_NAMES", "").split(",")
    if name.strip()
}
PAYMENT_BOSS_USER_IDS = {
    user_id.strip()
    for user_id in os.getenv("PAYMENT_BOSS_USER_IDS", "").split(",")
    if user_id.strip()
}
PAYMENT_BOSS_USERNAMES = {
    username.strip().lower().lstrip("@")
    for username in os.getenv("PAYMENT_BOSS_USERNAMES", "").split(",")
    if username.strip()
}
PAYMENT_BOSS_FULL_NAMES = {
    name.strip().lower()
    for name in os.getenv("PAYMENT_BOSS_FULL_NAMES", "").split(",")
    if name.strip()
}
PAYMENT_PERMISSION_DENIED = "❌ Bạn không có quyền thực hiện lệnh này."


def get_payment_worksheet():
    if not gs_client:
        return None

    spreadsheet_obj = gs_client.open("TF - Hệ Thống Vận Hành")
    try:
        return spreadsheet_obj.worksheet(PAYMENT_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        return None


def telegram_user_name(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "Không rõ"
    if user.username:
        return f"@{user.username}"
    return user.full_name or user.first_name or "Không rõ"


def parse_positive_amount(amount_text: str) -> int:
    normalized = amount_text.replace(".", "").replace(",", "").strip()
    amount = int(normalized)
    if amount <= 0:
        raise ValueError("Số tiền phải là số dương.")
    return amount


def format_vnd(amount: int) -> str:
    return f"{amount:,}đ".replace(",", ".")


def payment_amount_from_record(record: Dict[str, Any]) -> int:
    try:
        return int(str(record.get("Số tiền", "0")).replace(".", "").replace(",", "").strip() or 0)
    except Exception:
        return 0


def payment_status_text(status: str) -> str:
    status = str(status).strip()
    status_icons = {
        PAYMENT_STATUS_PENDING: "⏳",
        PAYMENT_STATUS_APPROVED: "✅",
        PAYMENT_STATUS_REJECTED: "❌",
        PAYMENT_STATUS_PAID: "💸",
    }
    return f"{status_icons.get(status, '•')} {status or 'Chưa rõ'}"


def parse_payment_date(date_text: str) -> Optional[datetime]:
    date_text = str(date_text).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_text, fmt).replace(tzinfo=TZ)
        except Exception:
            continue
    return None


def next_payment_id(rows: List[List[str]]) -> str:
    max_number = 0
    for row in rows[1:]:
        if not row:
            continue
        request_id = str(row[0]).strip().upper()
        if not request_id.startswith("DN"):
            continue
        try:
            max_number = max(max_number, int(request_id[2:]))
        except Exception:
            continue
    return f"DN{max_number + 1:03d}"


def payment_row_to_dict(row: List[str]) -> Dict[str, Any]:
    padded = row + [""] * (len(PAYMENT_HEADERS) - len(row))
    return dict(zip(PAYMENT_HEADERS, padded))


def find_payment_row(ws, request_id: str):
    rows = ws.get_all_values()
    normalized_id = request_id.strip().upper()
    for row_index, row in enumerate(rows[1:], start=2):
        current_id = str(row[0]).strip().upper() if row else ""
        if current_id == normalized_id:
            return row_index, payment_row_to_dict(row)
    return None, None


def payment_user_matches(update: Update, user_ids, usernames, full_names) -> bool:
    user = update.effective_user
    if not user:
        return False

    user_id = str(user.id) if user.id else ""
    username = (user.username or "").strip().lower().lstrip("@")
    full_name = (user.full_name or user.first_name or "").strip().lower()

    return (
        user_id in user_ids
        or username in usernames
        or full_name in full_names
    )


def is_payment_boss(update: Update) -> bool:
    return payment_user_matches(
        update,
        PAYMENT_BOSS_USER_IDS,
        PAYMENT_BOSS_USERNAMES,
        PAYMENT_BOSS_FULL_NAMES,
    )


def is_payment_approver(update: Update) -> bool:
    return payment_user_matches(
        update,
        PAYMENT_APPROVER_USER_IDS,
        PAYMENT_APPROVER_USERNAMES,
        PAYMENT_APPROVER_FULL_NAMES,
    )


def can_approve_payment(update: Update) -> bool:
    return is_payment_approver(update)


def can_pay_payment(update: Update) -> bool:
    return is_payment_approver(update)


def can_view_payment_report(update: Update) -> bool:
    return is_payment_boss(update)


def can_create_payment(update: Update) -> bool:
    if not PAYMENT_CREATOR_USER_IDS and not PAYMENT_CREATOR_USERNAMES and not PAYMENT_CREATOR_FULL_NAMES:
        return update.effective_user is not None

    return (
        payment_user_matches(
            update,
            PAYMENT_CREATOR_USER_IDS,
            PAYMENT_CREATOR_USERNAMES,
            PAYMENT_CREATOR_FULL_NAMES,
        )
        or is_payment_approver(update)
        or is_payment_boss(update)
    )


def build_payment_lines(records: List[Dict[str, Any]], title: str) -> str:
    lines = [title, ""]
    for index, row in enumerate(records, start=1):
        amount = payment_amount_from_record(row)
        lines.append(
            f"{index}. {row.get('Mã đề nghị', '')} - {payment_status_text(row.get('Trạng thái', ''))}"
        )
        lines.append(f"   👤 Người đề nghị: {row.get('Người đề nghị', '')}")
        lines.append(f"   🧾 Loại chi phí: {row.get('Loại chi phí', '')}")
        lines.append(f"   📝 Nội dung: {row.get('Nội dung', '')}")
        lines.append(f"   💰 Số tiền: {format_vnd(amount)}")
        lines.append("")
    return "\n".join(lines).strip()


def build_payment_detail(record: Dict[str, Any]) -> str:
    amount = payment_amount_from_record(record)
    lines = [
        f"📄 CHI TIẾT ĐỀ NGHỊ {record.get('Mã đề nghị', '')}",
        "",
        f"📅 Ngày đề nghị: {record.get('Ngày đề nghị', '') or 'Chưa có'}",
        f"👤 Người đề nghị: {record.get('Người đề nghị', '') or 'Chưa có'}",
        f"🧾 Loại chi phí: {record.get('Loại chi phí', '') or 'Chưa có'}",
        f"📝 Nội dung: {record.get('Nội dung', '') or 'Chưa có'}",
        f"💰 Số tiền: {format_vnd(amount)}",
        f"📌 Trạng thái: {payment_status_text(record.get('Trạng thái', ''))}",
        f"✅ Người duyệt: {record.get('Người duyệt', '') or 'Chưa có'}",
        f"📅 Ngày duyệt: {record.get('Ngày duyệt', '') or 'Chưa có'}",
        f"💸 Người thanh toán: {record.get('Người thanh toán', '') or 'Chưa có'}",
        f"📅 Ngày thanh toán: {record.get('Ngày thanh toán', '') or 'Chưa có'}",
        f"🗒 Ghi chú: {record.get('Ghi chú', '') or 'Không có'}",
    ]
    return "\n".join(lines)
def normalize_days(days: str) -> List[int]:
    days = days.strip().lower()
    if days == "daily":
        return list(range(7))
    if days == "weekdays":
        return [0, 1, 2, 3, 4]
    if days == "weekends":
        return [5, 6]
    result = []
    for d in days.split(","):
        d = d.strip().lower()
        if d not in DAY_MAP:
            continue
        result.append(DAY_MAP[d])
    return sorted(set(result))

def days_to_text(days: List[int]) -> str:
    if days == list(range(7)):
        return "daily"
    if days == [0,1,2,3,4]:
        return "weekdays"
    if days == [5,6]:
        return "weekends"
    return ",".join(DAY_LABEL[d] for d in days)

def parse_times(times_str: str) -> List[str]:
    times = []
    for t in times_str.split(","):
        t = t.strip()
        parts = t.split(":")
        if len(parts) != 2:
            raise ValueError("Giờ phải dạng HH:MM, ví dụ 06:38 hoặc 08:00,18:00")
        hh, mm = int(parts[0]), int(parts[1])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError("Giờ không hợp lệ.")
        times.append(f"{hh:02d}:{mm:02d}")
    return times

SENT_KEYS = set()

async def check_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(TZ)
    today = now.weekday()
    current_time = now.strftime("%H:%M")
    today_key = now.strftime("%Y-%m-%d")

    chats = DATA.get("chats", {})

    for chat_id, reminders in chats.items():
        for idx, item in enumerate(reminders, start=1):
            if current_time not in item.get("times", []):
                continue

            if today not in item.get("days", []):
                continue

            key = f"{today_key}:{chat_id}:{idx}:{current_time}"

            if key in SENT_KEYS:
                continue

            SENT_KEYS.add(key)

            await context.bot.send_message(
                chat_id=int(chat_id),
                text=f"⏰ {item['text']}"
            )
            if "DONE " in item["text"].upper():
                    done_key = extract_done_key(item["text"])

                    context.job_queue.run_once(
                    check_followup,
                    when=15 * 60,
                    data={
                        "chat_id": int(chat_id),
                        "task_name": done_key,
                        "done_key": done_key,
                    },
                    name=f"followup:{chat_id}:{idx}:{current_time}",
                )
            if len(SENT_KEYS) > 2000:
                SENT_KEYS.clear()


def clear_jobs_for_chat(app: Application, chat_id: str) -> None:
    return


def schedule_chat(app: Application, chat_id: str) -> None:
    schedule_all(app)


def schedule_all(app: Application) -> None:
    for job in app.job_queue.jobs():
        if job.name in ("check_reminders", "daily_report"):
            job.schedule_removal()

    app.job_queue.run_repeating(
        check_reminders,
        interval=30,
        first=5,
        name="check_reminders",
    )
    app.job_queue.run_daily(
        daily_report,
        time=time(hour=22, minute=0, tzinfo=TZ),
        name="daily_report",
    )
    log.info("Reminder checker started")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    DATA.setdefault("chats", {}).setdefault(chat_id, [])
    save_data(DATA)
    await update.message.reply_text(
        "Bot TF sẵn sàng.\n\n"
        "Lệnh:\n"
        "/addat <giờ> <ngày> <nội dung>\n"
        "Ví dụ: /addat 06:38 mon,tue,wed Mở ca\n"
        "/list\n/remove <số>\n/clear\n/now\n/help\n\n"
        "Đề nghị thanh toán:\n"
        "/paymentrequest LOAI_CHI_PHI SO_TIEN NOI_DUNG\n"
        "/paymentlist\n/paymentdetail ID\n/paymentpending\n"
        "/paymentapprove ID\n/paymentreject ID Lý_do\n/paymentpaid ID\n"
        "/paymentreport week|month"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)

async def addat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    parts = text.split(maxsplit=3)
    if len(parts) < 4:
        await update.message.reply_text("Dùng: /addat <giờ> <ngày> <nội dung>\nVD: /addat 06:38 weekdays Mở ca")
        return
    _, times_str, days_str, reminder_text = parts
    try:
        times = parse_times(times_str)
        days = normalize_days(days_str)
    except Exception as e:
        await update.message.reply_text(f"Lỗi: {e}")
        return

    chat_id = str(update.effective_chat.id)
    DATA.setdefault("chats", {}).setdefault(chat_id, []).append({
        "times": times,
        "days": days,
        "text": reminder_text,
    })
    save_data(DATA)
    schedule_chat(context.application, chat_id)
    await update.message.reply_text(f"Đã thêm: {reminder_text} [{','.join(times)} · {days_to_text(days)}]")

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    reminders = DATA.get("chats", {}).get(chat_id, [])
    if not reminders:
        await update.message.reply_text("Chưa có lịch nhắc. Dùng /addat để thêm.")
        return
    lines = ["Danh sách lịch:"]
    for i, r in enumerate(reminders, start=1):
        lines.append(f"{i}. {r['text']} [{','.join(r['times'])} · {days_to_text(r['days'])}]")
    await update.message.reply_text("\n".join(lines))

async def remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    reminders = DATA.get("chats", {}).get(chat_id, [])
    if not context.args:
        await update.message.reply_text("Dùng: /remove <số>")
        return
    try:
        idx = int(context.args[0]) - 1
        removed = reminders.pop(idx)
    except Exception:
        await update.message.reply_text("Số không hợp lệ. Gõ /list để xem số.")
        return
    save_data(DATA)
    schedule_chat(context.application, chat_id)
    await update.message.reply_text(f"Đã xóa: {removed['text']}")

async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    DATA.setdefault("chats", {})[chat_id] = []
    save_data(DATA)
    clear_jobs_for_chat(context.application, chat_id)
    await update.message.reply_text("Đã xóa sạch lịch của chat này.")

async def now_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    reminders = DATA.get("chats", {}).get(chat_id, [])
    if not reminders:
        await update.message.reply_text("Reminder check-in: danh sách đang trống.")
        return
    lines = ["Reminder check-in:"]
    for i, r in enumerate(reminders, start=1):
        lines.append(f"{i}. {r['text']} [{','.join(r['times'])} · {days_to_text(r['days'])}]")
    await update.message.reply_text("\n".join(lines))
def build_daily_report(chat_id: str):
    today_key = datetime.now(TZ).strftime("%Y-%m-%d")
    today = datetime.now(TZ).weekday()

    reminders = DATA.get("chats", {}).get(chat_id, [])
    done_today = DATA.get("done", {}).get(chat_id, {}).get(today_key, {})

    expected = []

    for item in reminders:
        text = item.get("text", "")

        if today not in item.get("days", []):
            continue

        if "DONE " not in text.upper():
            continue

        done_key = extract_done_key(text)

        if done_key and done_key not in expected:
            expected.append(done_key)

    if not expected:
        return None

    lines = ["📊 BÁO CÁO TF HÔM NAY", ""]
    done_count = 0

    for key in expected:
        if key in done_today:
            staff = done_today[key].get("staff", "Nhân viên")
            done_time = done_today[key].get("time", "--:--")
            lines.append(f"✅ {key}: {staff} - {done_time}")
            done_count += 1
        else:
            lines.append(f"❌ {key}: Chưa DONE")

    lines.append("")
    lines.append(f"Hoàn thành: {done_count}/{len(expected)}")

    if done_count < len(expected):
        lines.append("Nếu có mục ❌, quản lý kiểm tra lại ca hôm nay.")

    return "\n".join(lines)          


async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    report = build_daily_report(chat_id)

    if not report:
        await update.message.reply_text("Hôm nay chưa có mục vận hành cần báo cáo.")
        return

    await update.message.reply_text(report)


async def daily_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    chats = DATA.get("chats", {})

    for chat_id in chats.keys():
        report = build_daily_report(str(chat_id))

        if not report:
            continue

        await context.bot.send_message(
            chat_id=int(chat_id),
            text=report
        )
def extract_done_key(text: str) -> str:
    upper_text = text.upper()
    marker = "DONE "

    if marker not in upper_text:
        return text.strip().upper()

    start = upper_text.find(marker) + len(marker)
    tail = text[start:].strip()

    if " - " in tail:
        tail = tail.split(" - ", 1)[0]

    return tail.strip().upper()
async def check_followup(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    chat_id = str(job.data["chat_id"])
    task_name = job.data["task_name"]
    done_key = job.data["done_key"]
    today_key = datetime.now(TZ).strftime("%Y-%m-%d")

    done_today = DATA.get("done", {}).get(chat_id, {}).get(today_key, {})

    if done_key in done_today:
        return

    await context.bot.send_message(
        chat_id=int(chat_id),
        text=f"🔁 Chưa thấy DONE {task_name}.\nNhân viên ca này xác nhận giúp sếp."
    )
def staff_in_today_shift(chat_id: str, staff_name: str) -> bool:
    day_keys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    today_key = day_keys[datetime.now(TZ).weekday()]

    today_shifts = DATA.get("shifts", {}).get(chat_id, {}).get(today_key, {})

    if not today_shifts:
        return False

    for assigned_staff in today_shifts.values():
        if assigned_staff.strip() == staff_name.strip():
            return True

    return False    
async def handle_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    kho_ws = None
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    text_upper = text.upper()
    chat_id = str(update.effective_chat.id)
    today_key = datetime.now(TZ).strftime("%Y-%m-%d")
    now = datetime.now(TZ).strftime("%H:%M")
    if text_upper.startswith("NHẬP HÀNG"):
        ws = get_worksheet("08_Nhap_Hang")

        if not ws:
            await update.message.reply_text("❌ Không kết nối được sheet 08_Nhap_Hang.")
            return

        def get_value(label):
            for line in text.splitlines():
                if line.lower().startswith(label.lower() + ":"):
                    return line.split(":", 1)[1].strip()
            return ""

        mat_hang = get_value("Mặt hàng")
        so_luong = get_value("Số lượng")
        don_gia = get_value("Đơn giá")
        tong_tien = get_value("Tổng tiền")
        nha_cung_cap = get_value("Nhà cung cấp")
        han_su_dung = get_value("Hạn sử dụng")
        nguoi_duyet = get_value("Người duyệt")
        ghi_chu = get_value("Ghi chú")

        if not mat_hang:
            await update.message.reply_text("❌ Mặt hàng không được để trống.")
            return

        so_luong_text = so_luong.strip()
        if not so_luong_text.isdigit():
            await update.message.reply_text("❌ Số lượng nhập phải là số nguyên.")
            return

        so_luong_int = int(so_luong_text)

        if so_luong_int <= 0:
            await update.message.reply_text("❌ Số lượng nhập phải lớn hơn 0.")
            return

        if not tong_tien:
            tong_tien = "Chưa nhập"

        if not nguoi_duyet:
            nguoi_duyet = "Chưa nhập"

        kho_ws = None
        try:
            kho_ws = get_worksheet("07_Quan_Ly_Kho")
        except Exception as e:
            print("LOI MO SHEET KHO:", e)

        if kho_ws is None:
            await update.message.reply_text("❌ Không kết nối được sheet 07_Quan_Ly_Kho.")
            return

        rows = kho_ws.get_all_values()
        found = False

        for idx, row in enumerate(rows[1:], start=2):
            ten_hang = row[0].strip().lower() if len(row) > 0 else ""
            print("SHEET =", repr(ten_hang))
            print("INPUT =", repr(mat_hang.strip().lower()))

            if ten_hang == mat_hang.strip().lower():
                found = True
                ton_cu = int(row[1]) if len(row) > 1 and row[1] else 0
                ton_moi = ton_cu + so_luong_int

                don_vi = row[2] if len(row) > 2 else ""
                ton_toi_thieu = int(row[3]) if len(row) > 3 and row[3] else 0

                trang_thai = "Sắp hết" if ton_moi <= ton_toi_thieu else "Đủ hàng"

                kho_ws.update_cell(idx, 2, ton_moi)
                kho_ws.update_cell(idx, 5, trang_thai)

                print("CAP NHAT KHO:", mat_hang, ton_cu, "+", so_luong, "=", ton_moi)

                break
        if not found:
                kho_ws.append_row(
                    [
                        mat_hang,
                        so_luong_int,
                        "",
                        0,
                        "Đủ hàng",
                    ],
                    value_input_option="RAW",
                    insert_data_option="INSERT_ROWS"
                )
                print("TAO MAT HANG MOI:", mat_hang, so_luong)

        ws.append_row(
            [
                datetime.now(TZ).strftime("%d/%m/%Y"),
                mat_hang,
                so_luong,
                don_gia,
                tong_tien,
                nha_cung_cap,
                han_su_dung,
                nguoi_duyet,
                ghi_chu,
            ],
            value_input_option="RAW",
            insert_data_option="INSERT_ROWS"
        )

        await update.message.reply_text(
            f"✅ Đã ghi nhận nhập hàng\n\n"
            f"📦 Mặt hàng: {mat_hang}\n"
            f"📥 Số lượng: {so_luong}\n"
            f"💰 Tổng tiền: {tong_tien}\n"
            f"👤 Người duyệt: {nguoi_duyet}"
        )
        return
    if text_upper.startswith("THIẾU HÀNG"):
        ws = get_worksheet("09_Bao_Thieu")

        if not ws:
            await update.message.reply_text("❌ Không kết nối được sheet 09_Bao_Thieu.")
            return

        def get_value(label):
            for line in text.splitlines():
                if line.lower().startswith(label.lower() + ":"):
                    return line.split(":", 1)[1].strip()
            return ""

        mat_hang = get_value("Mặt hàng")
        so_luong_con = get_value("Số lượng còn")
        muc_do = get_value("Mức độ")
        du_kien = get_value("Dự kiến đủ dùng đến")
        de_xuat = get_value("Đề xuất nhập thêm")
        ghi_chu = get_value("Ghi chú")

        if not mat_hang or not so_luong_con or not muc_do:
            await update.message.reply_text(
                "⚠️ BÁO THIẾU HÀNG CHƯA ĐỦ THÔNG TIN\n\n"
                "Vui lòng điền tối thiểu:\n"
                "- Mặt hàng\n"
                "- Số lượng còn\n"
                "- Mức độ"
            )
            return

        ws.append_row(
            [
                datetime.now(TZ).strftime("%d/%m/%Y"),
                mat_hang,
                so_luong_con,
                muc_do,
                du_kien,
                de_xuat,
                ghi_chu
            ],
            value_input_option="RAW",
            insert_data_option="INSERT_ROWS"
        )

        await update.message.reply_text(
            f"⚠️ Đã ghi nhận báo thiếu hàng\n\n"
            f"📦 Mặt hàng: {mat_hang}\n"
            f"📉 Còn lại: {so_luong_con}\n"
            f"🚨 Mức độ: {muc_do}\n"
            f"➕ Đề xuất nhập: {de_xuat}"
        )
        return
    if text_upper.startswith("XUẤT KHO"):
        ws = get_worksheet("11_Xuat_Kho")
        kho_ws = get_worksheet("07_Quan_Ly_Kho")

        if not ws:
            await update.message.reply_text("❌ Không kết nối được sheet 11_Xuat_Kho.")
            return

        if not kho_ws:
            await update.message.reply_text("❌ Không kết nối được sheet 07_Quan_Ly_Kho.")
            return

        def get_value(label):
            for line in text.splitlines():
                if line.lower().startswith(label.lower() + ":"):
                    return line.split(":", 1)[1].strip()
            return ""

        mat_hang = get_value("Mặt hàng")
        so_luong_xuat = get_value("Số lượng xuất")
        ly_do = get_value("Lý do")
        ca = get_value("Ca")
        ghi_chu = get_value("Ghi chú")

        if not mat_hang or not so_luong_xuat:
            await update.message.reply_text(
                "⚠️ BÁO XUẤT KHO CHƯA ĐỦ THÔNG TIN\n\n"
                "Vui lòng điền tối thiểu:\n"
                "Mặt hàng:\n"
                "Số lượng xuất:"
            )
            return

        try:
            so_luong_xuat_int = int(
                so_luong_xuat
                .replace(".", "")
                .replace(",", "")
                .strip()
            )
        except Exception:
            await update.message.reply_text("❌ Số lượng xuất không hợp lệ.")
            return

        if so_luong_xuat_int <= 0:
            await update.message.reply_text("❌ Số lượng xuất phải lớn hơn 0.")
            return

        rows = kho_ws.get_all_values()
        found_row = None
        found_index = None

        for idx, row in enumerate(rows[1:], start=2):
            ten_hang = row[0].strip().lower() if len(row) > 0 else ""

            if ten_hang == mat_hang.strip().lower():
                found_row = row
                found_index = idx
                break

        if not found_row:
            await update.message.reply_text("Mặt hàng chưa tồn tại trong kho")
            return

        try:
            ton_cu = int(found_row[1]) if len(found_row) > 1 and found_row[1] else 0
        except Exception:
            await update.message.reply_text("❌ Tồn kho hiện tại không hợp lệ.")
            return

        if so_luong_xuat_int > ton_cu:
            await update.message.reply_text("Không đủ tồn kho để xuất")
            return

        ton_moi = ton_cu - so_luong_xuat_int
        try:
            ton_toi_thieu = int(found_row[3]) if len(found_row) > 3 and found_row[3] else 0
        except Exception:
            ton_toi_thieu = 0

        trang_thai = "Sắp hết" if ton_moi <= ton_toi_thieu else "Đủ hàng"

        kho_ws.update_cell(found_index, 2, ton_moi)
        kho_ws.update_cell(found_index, 5, trang_thai)

        ws.append_row(
            [
                datetime.now(TZ).strftime("%d/%m/%Y"),
                mat_hang,
                so_luong_xuat,
                ly_do,
                ca,
                ghi_chu
            ],
            value_input_option="RAW",
            insert_data_option="INSERT_ROWS"
        )
        await update.message.reply_text(
            f"📤 Đã ghi nhận xuất kho\n\n"
            f"📦 Mặt hàng: {mat_hang}\n"
            f"📉 Số lượng xuất: {so_luong_xuat}\n"
            f"📋 Lý do: {ly_do}\n"
            f"🕒 Ca: {ca}"
        )

        return
    if text_upper.startswith("CHECKIN"):
        staff_name = text.split("-", 1)[1].strip() if "-" in text else text[7:].strip()
        staff_name = staff_name.strip().title()
        staff_sheet = get_worksheet("00_Nhan_Vien")
        staff_list = []

        if staff_sheet:
            staff_rows = staff_sheet.get_all_records()

            for row in staff_rows:
                name = str(row.get("Tên nhân viên", "")).strip().title()
                status = str(row.get("Trạng thái", "")).strip().lower()

                if name and status == "active":
                    staff_list.append(name)
        print("STAFF LIST:", staff_list)
        print("STAFF NAME:", staff_name)
        if not staff_name:
            await update.message.reply_text("❌ Vui lòng ghi đúng: CHECKIN Tên")
            return

        unknown_staff = staff_name not in staff_list
        if unknown_staff:
            await update.message.reply_text(
                f"⚠️ {staff_name} chưa có trong danh sách nhân viên.\n"
                "Bot vẫn ghi tạm. Mr.Win cần kiểm tra và duyệt lại."
            )
        attendance_today = DATA.get("attendance", {}).get(chat_id, {}).get(today_key, {})

        if (
            staff_name in attendance_today
            and attendance_today[staff_name].get("checkin")
            and not attendance_today[staff_name].get("checkout")
        ):
            await update.message.reply_text(
                f"⚠️ {staff_name} đang trong ca làm.\n"
                "Vui lòng CHECKOUT trước."
            )
            return
        DATA.setdefault("attendance", {}).setdefault(chat_id, {}).setdefault(today_key, {}).setdefault(staff_name, {})
        DATA["attendance"][chat_id][today_key][staff_name]["checkin"] = now
        save_data(DATA)
        if gs_client:
            sheet = get_worksheet("01_Cham_Cong")
            print("CHECKIN SHEET:", sheet.title if sheet else None)

            if sheet:
                new_row = [
                    datetime.now(TZ).strftime("%d/%m/%Y"),
                    staff_name,
                    now,
                    "",
                    "",
                    "",
                    "Tên chưa duyệt" if unknown_staff else ""
                ]

                sheet.append_row(
                    new_row,
                    value_input_option="RAW",
                    insert_data_option="INSERT_ROWS"
                )

                
        await update.message.reply_text(
            f"✅ Đã ghi nhận CHECKIN: {staff_name} lúc {now}"
        )
        return


    if text_upper.startswith("CHECKOUT"):
        staff_name = text.split("-", 1)[1].strip() if "-" in text else text[8:].strip()
        staff_name = staff_name.strip().title()
        staff_sheet = get_worksheet("00_Nhan_Vien")
        staff_list = []

        if staff_sheet:
            staff_rows = staff_sheet.get_all_records()

            for row in staff_rows:
                name = str(row.get("Tên nhân viên", "")).strip().title()
                status = str(row.get("Trạng thái", "")).strip().lower()

                if name and status == "active":
                    staff_list.append(name)
        print("STAFF LIST:", staff_list)
        print("STAFF NAME:", staff_name)
        if not staff_name:
            await update.message.reply_text("❌ Vui lòng ghi đúng: CHECKOUT Tên")
            return

        unknown_staff = staff_name not in staff_list

        if unknown_staff:
            await update.message.reply_text(
                f"⚠️ {staff_name} chưa có trong danh sách nhân viên.\n"
                "Bot vẫn ghi tạm. Mr.Win cần kiểm tra và duyệt lại."
        )
        
        
        DATA.setdefault("attendance", {}).setdefault(chat_id, {}).setdefault(today_key, {}).setdefault(staff_name, {})
        DATA.setdefault("attendance", {}).setdefault(chat_id, {}).setdefault(today_key, {}).setdefault(staff_name, {})
        DATA["attendance"][chat_id][today_key][staff_name]["checkout"] = now
        save_data(DATA)
        if gs_client:
            sheet = get_worksheet("01_Cham_Cong")
            print("CHECKOUT SHEET:", sheet.title if sheet else None)

            if sheet:

                records = sheet.get_all_records()

                for idx in range(len(records) - 1, -1, -1):
                    row = records[idx]
                    i = idx + 2
                    if (
                        row["Ngày"] == datetime.now(TZ).strftime("%d/%m/%Y")
                        and str(row["Nhân viên"]).strip().lower() == staff_name.lower()
                        and not str(row.get("Checkout", "")).strip()
                    ):
                        sheet.update_cell(i, 4, now)

                        checkin_time = datetime.strptime(row["Checkin"], "%H:%M")
                        checkout_time = datetime.strptime(now, "%H:%M")
                        total_hours = round((checkout_time - checkin_time).seconds / 3600, 2)

                        sheet.format("E:E", {
                            "numberFormat": {
                                "type": "NUMBER",
                                "pattern": "0.00"
                            }
                        })

                        sheet.update(
                            f"E{i}",
                            [[float(total_hours)]],
                            value_input_option="RAW"
                        )
                        total_minutes = int((checkout_time - checkin_time).seconds / 60)
                        hours = total_minutes // 60
                        minutes = total_minutes % 60

                        if hours > 0 and minutes > 0:
                            duration_text = f"{hours} giờ {minutes} phút"
                        elif hours > 0:
                            duration_text = f"{hours} giờ"
                        else:
                            duration_text = f"{minutes} phút"

                        sheet.update_cell(i, 6, duration_text)
                        break
        await update.message.reply_text(
            f"✅ Đã ghi nhận CHECKOUT: {staff_name} lúc {now}"
        )
        return

    if text_upper.startswith("DONE "):
        body = text[5:].strip()

        if " - " in body:
            task_name, staff_name = body.split(" - ", 1)
        else:
            task_name = body
            staff_name = update.effective_user.first_name or "Nhân viên"

        task_name = task_name.strip()
        staff_name = staff_name.strip()

        if not task_name:
            await update.message.reply_text("❌ Vui lòng ghi đúng: DONE TÊN VIỆC - Tên nhân viên")
            return

        done_key = task_name.upper()

        DATA.setdefault("done", {}).setdefault(chat_id, {}).setdefault(today_key, {})
        DATA["done"][chat_id][today_key][done_key] = {
            "staff": staff_name,
            "time": now,
        }
        save_data(DATA)

        await update.message.reply_text(
            f"✅ Đã ghi nhận: {staff_name} hoàn thành {task_name} lúc {now}"
        )
        return
    if text_upper.startswith("THIẾU HÀNG -"):
        def get_field(field_name: str) -> str:
            for line in text.splitlines():
                if line.lower().startswith(field_name.lower() + ":"):
                    return line.split(":", 1)[1].strip()
            return ""

        first_line = text.splitlines()[0]
        reporter = first_line.replace("THIẾU HÀNG -", "").strip()

        item = get_field("Mặt hàng")
        remaining = get_field("Số lượng còn")
        level = get_field("Mức độ")
        enough_until = get_field("Dự kiến đủ dùng đến")
        suggested = get_field("Đề xuất nhập thêm")
        note = get_field("Ghi chú")

        if not item or not remaining or not level:
            await update.message.reply_text(
                "⚠️ BÁO THIẾU HÀNG CHƯA ĐỦ THÔNG TIN\n\n"
                "Vui lòng điền tối thiểu:\n"
                "Mặt hàng:\n"
                "Số lượng còn:\n"
                "Mức độ:"
            )
            return

        await update.message.reply_text(
            "✅ ĐÃ GHI NHẬN BÁO THIẾU HÀNG\n\n"
            f"Người báo: {reporter or 'Chưa ghi'}\n"
            f"Mặt hàng: {item}\n"
            f"Số lượng còn: {remaining}\n"
            f"Mức độ: {level}\n"
            f"Dự kiến đủ dùng đến: {enough_until or 'Chưa ghi'}\n"
            f"Đề xuất nhập thêm: {suggested or 'Chưa ghi'}\n"
            f"Ghi chú: {note or 'Không có'}\n\n"
            "Miss Uyên vui lòng kiểm tra và duyệt hướng xử lý.\n"
            "Mr.Happy / Mr.Win hỗ trợ đối chiếu kho và chi phí."
        )
        return
    if text_upper.startswith("NHẬP HÀNG -"):
        def get_field(field_name: str) -> str:
            for line in text.splitlines():
                if line.lower().startswith(field_name.lower() + ":"):
                    return line.split(":", 1)[1].strip()
            return ""

        first_line = text.splitlines()[0]
        importer = first_line.replace("NHẬP HÀNG -", "").strip()

        item = get_field("Mặt hàng")
        quantity = get_field("Số lượng")
        unit_price = get_field("Đơn giá")
        total = get_field("Tổng tiền")
        supplier = get_field("Nhà cung cấp")
        expiry = get_field("Hạn sử dụng")
        approver = get_field("Người duyệt")
        note = get_field("Ghi chú")
        fifo_stock = DATA.setdefault("fifo_stock", {})
        if not item or not quantity:
            await update.message.reply_text(
                "⚠️ BÁO NHẬP HÀNG CHƯA ĐỦ THÔNG TIN\n\n"
                "Vui lòng điền tối thiểu:\n"
                "Mặt hàng:\n"
                "Số lượng:"
            )
            return

        await update.message.reply_text(
            "✅ ĐÃ GHI NHẬN NHẬP HÀNG\n\n"
            f"Người nhập: {importer or 'Chưa ghi'}\n"
            f"Mặt hàng: {item}\n"
            f"Số lượng: {quantity}\n"
            f"Đơn giá: {unit_price or 'Chưa ghi'}\n"
            f"Tổng tiền: {total or 'Chưa ghi'}\n"
            f"Nhà cung cấp: {supplier or 'Chưa ghi'}\n"
            f"Hạn sử dụng: {expiry or 'Chưa ghi'}\n"
            f"Người duyệt: {approver or 'Miss Uyên'}\n"
            f"Ghi chú: {note or 'Không có'}\n\n"
            "Miss Uyên vui lòng kiểm tra và xác nhận nhập kho.\n"
            "Mr.Happy / Mr.Win hỗ trợ đối chiếu chi phí nếu cần."
        )
        return      
    if text_upper.startswith("XUẤT KHO -"):
        def get_field(field_name: str) -> str:
            for line in text.splitlines():
                if line.lower().startswith(field_name.lower() + ":"):
                    return line.split(":", 1)[1].strip()
            return ""

        first_line = text.splitlines()[0]
        exporter = first_line.replace("XUẤT KHO -", "").strip()

        item = get_field("Mặt hàng")
        quantity = get_field("Số lượng xuất")
        reason = get_field("Lý do")
        shift = get_field("Ca")
        note = get_field("Ghi chú")

        if not item or not quantity:
            await update.message.reply_text(
                "⚠️ BÁO XUẤT KHO CHƯA ĐỦ THÔNG TIN\n\n"
                "Vui lòng điền tối thiểu:\n"
                "Mặt hàng:\n"
                "Số lượng xuất:"
            )
            return

        await update.message.reply_text(
            "✅ ĐÃ GHI NHẬN XUẤT KHO\n\n"
            f"Người xuất: {exporter or 'Chưa ghi'}\n"
            f"Mặt hàng: {item}\n"
            f"Số lượng xuất: {quantity}\n"
            f"Lý do: {reason or 'Chưa ghi'}\n"
            f"Ca: {shift or 'Chưa ghi'}\n"
            f"Ghi chú: {note or 'Không có'}\n\n"
            "Mr.Happy / Mr.Win vui lòng đối chiếu tồn kho cuối ca.\n"
            "Miss Uyên kiểm tra nếu phát sinh lệch kho."
        )
        return
    if text_upper.startswith("KIỂM KHO -"):
        def get_field(field_name: str) -> str:
            for line in text.splitlines():
                if line.lower().startswith(field_name.lower() + ":"):
                    return line.split(":", 1)[1].strip()
            return ""

        first_line = text.splitlines()[0]
        check_date = first_line.replace("KIỂM KHO -", "").strip()

        checker = get_field("Người kiểm")
        enough_items = get_field("Các món còn đủ")
        low_items = get_field("Các món sắp hết")
        need_import = get_field("Các món cần nhập")
        near_expiry = get_field("Hàng gần hết hạn")
        damaged = get_field("Hàng hư hao / thất thoát nếu có")
        note = get_field("Ghi chú")

        if not checker:
            await update.message.reply_text(
                "⚠️ KIỂM KHO CHƯA ĐỦ THÔNG TIN\n\n"
                "Vui lòng điền tối thiểu:\n"
                "Người kiểm:\n"
                "Các món sắp hết:\n"
                "Các món cần nhập:"
            )
            return

        alert_text = ""
        if low_items:
            alert_text = (
                "\n\n⚠️ CẢNH BÁO HÀNG SẮP HẾT\n"
                f"{low_items}"
            )

        expiry_alert_text = ""
        if near_expiry:
            expiry_alert_text = (
                "\n\n🗓️ CẢNH BÁO HÀNG GẦN HẾT HẠN\n"
                f"{near_expiry}"
            )

        await update.message.reply_text(
            "✅ ĐÃ GHI NHẬN KIỂM KHO\n\n"
            f"Ngày kiểm: {check_date or 'Chưa ghi'}\n"
            f"Người kiểm: {checker or 'Chưa ghi'}\n"
            f"Các món còn đủ: {enough_items or 'Chưa ghi'}\n"
            f"Các món sắp hết: {low_items or 'Không có'}\n"
            f"Các món cần nhập: {need_import or 'Không có'}\n"
            f"Hàng gần hết hạn: {near_expiry or 'Không có'}\n"
            f"Hư hao / thất thoát: {damaged or 'Không có'}\n"
            f"Ghi chú: {note or 'Không có'}"
            f"{alert_text}"
            f"{expiry_alert_text}\n\n"
            "Miss Uyên vui lòng kiểm tra và duyệt hướng xử lý nếu cần nhập hàng.\n"
            "Mr.Happy / Mr.Win hỗ trợ đối chiếu kho."
        )
        return
async def shift_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    args = context.args

    if len(args) < 3:
        await update.message.reply_text(
            "Cách dùng: /shift <ngày> <ca> <tên>\n"
            "Ví dụ: /shift mon sang Huy\n"
            "Ngày: mon,tue,wed,thu,fri,sat,sun\n"
            "Ca: sang hoặc toi"
        )
        return

    day = args[0].lower()
    shift = args[1].lower()
    staff = " ".join(args[2:]).strip()

    day_names = {
        "mon": "T2",
        "tue": "T3",
        "wed": "T4",
        "thu": "T5",
        "fri": "T6",
        "sat": "T7",
        "sun": "CN",
    }

    shift_names = {
        "sang": "Sáng",
        "toi": "Tối",
    }

    if day not in day_names:
        await update.message.reply_text("Ngày chưa đúng. Dùng: mon,tue,wed,thu,fri,sat,sun")
        return

    if shift not in shift_names:
        await update.message.reply_text("Ca chưa đúng. Dùng: sang hoặc toi")
        return

    DATA.setdefault("shifts", {}).setdefault(chat_id, {}).setdefault(day, {})
    DATA["shifts"][chat_id][day][shift] = staff
    save_data(DATA)

    await update.message.reply_text(
        f"✅ Đã xếp lịch: {day_names[day]} - Ca {shift_names[shift]}: {staff}"
    )

async def ranh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args

    if len(args) < 3:
        await update.message.reply_text(
            "Cách dùng: /ranh <ngày> <ca> <tên>\n"
            "Ví dụ: /ranh t2 sang Huy\n"
            "Ngày: t2,t3,t4,t5,t6,t7,cn\n"
            "Ca: sang hoặc toi"
        )
        return

    day = args[0].lower()
    shift = args[1].lower()
    staff = " ".join(args[2:]).strip()

    day_names = {
        "t2": "T2",
        "t3": "T3",
        "t4": "T4",
        "t5": "T5",
        "t6": "T6",
        "t7": "T7",
        "cn": "CN",
    }

    shift_names = {
        "sang": "Sáng",
        "toi": "Tối",
    }

    if day not in day_names:
        await update.message.reply_text("Ngày chưa đúng. Dùng: t2,t3,t4,t5,t6,t7,cn")
        return

    if shift not in shift_names:
        await update.message.reply_text("Ca chưa đúng. Dùng: sang hoặc toi")
        return

    now_dt = datetime.now(TZ)
    week_key = now_dt.strftime("%Y-W%U")

    day_to_weekday = {
        "t2": 0,
        "t3": 1,
        "t4": 2,
        "t5": 3,
        "t6": 4,
        "t7": 5,
        "cn": 6,
    }

    days_ahead = day_to_weekday[day] - now_dt.weekday()
    if days_ahead < 0:
        days_ahead += 7

    target_date = now_dt + timedelta(days=days_ahead)
    today = target_date.strftime("%d/%m/%Y")

    sheet = get_worksheet("11_lich_ranh")
    if not sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet 11_lich_ranh.")
        return

    sheet.append_row(
        [
            week_key,
            today,
            day_names[day],
            shift_names[shift],
            staff,
            "AVAILABLE",
            "",
        ],
        value_input_option="RAW",
        insert_data_option="INSERT_ROWS",
    )

    await update.message.reply_text(
        f"✅ Đã ghi lịch rảnh:\n"
        f"{staff} - {day_names[day]} - Ca {shift_names[shift]}"
    )
async def checkranh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sheet = get_worksheet("11_lich_ranh")
    if not sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet 11_lich_ranh.")
        return

    try:
        records = sheet.get_all_records()
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc 11_lich_ranh:\n{e}")
        return

    if not records:
        await update.message.reply_text("📋 Chưa có dữ liệu lịch rảnh.")
        return

    now_dt = datetime.now(TZ)
    week_key = now_dt.strftime("%Y-W%U")

    day_order = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
    shift_order = ["Sáng", "Tối"]

    grouped = {}

    for row in records:
        if str(row.get("Tuần", "")).strip() != week_key:
            continue

        if str(row.get("Trạng thái", "")).strip().upper() != "AVAILABLE":
            continue

        day = str(row.get("Thứ", "")).strip()
        shift = str(row.get("Ca", "")).strip()
        staff = str(row.get("Nhân viên", "")).strip()

        if not day or not shift or not staff:
            continue

        grouped.setdefault(day, {}).setdefault(shift, [])
        if staff not in grouped[day][shift]:
            grouped[day][shift].append(staff)

    if not grouped:
        await update.message.reply_text("📋 Tuần này chưa có ai báo lịch rảnh.")
        return

    lines = [f"📋 LỊCH RẢNH TUẦN {week_key}", ""]

    for day in day_order:
        if day not in grouped:
            continue

        lines.append(f"{day}:")

        for shift in shift_order:
            staff_list = grouped.get(day, {}).get(shift, [])
            if staff_list:
                lines.append(f"- Ca {shift}: {', '.join(staff_list)}")

        lines.append("")

    await update.message.reply_text("\n".join(lines))
async def xepca_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args

    if len(args) < 3:
        await update.message.reply_text(
            "Cách dùng: /xepca <ngày> <ca> <tên>\n"
            "Ví dụ: /xepca t2 sang Huy\n"
            "Ngày: t2,t3,t4,t5,t6,t7,cn\n"
            "Ca: sang hoặc toi"
        )
        return

    day = args[0].lower()
    shift = args[1].lower()
    staff = " ".join(args[2:]).strip()

    day_names = {
        "t2": "T2", "t3": "T3", "t4": "T4",
        "t5": "T5", "t6": "T6", "t7": "T7", "cn": "CN",
    }

    shift_names = {
        "sang": "Sáng",
        "toi": "Tối",
    }

    if day not in day_names:
        await update.message.reply_text("Ngày chưa đúng. Dùng: t2,t3,t4,t5,t6,t7,cn")
        return

    if shift not in shift_names:
        await update.message.reply_text("Ca chưa đúng. Dùng: sang hoặc toi")
        return

    now_dt = datetime.now(TZ)
    week_key = now_dt.strftime("%Y-W%U")

    day_to_weekday = {
        "t2": 0, "t3": 1, "t4": 2,
        "t5": 3, "t6": 4, "t7": 5, "cn": 6,
    }

    days_ahead = day_to_weekday[day] - now_dt.weekday()
    if days_ahead < 0:
        days_ahead += 7

    target_date = now_dt + timedelta(days=days_ahead)
    work_date = target_date.strftime("%d/%m/%Y")

    start_time = ""
    end_time = ""
    location = "TF Home"

    config_sheet = get_worksheet("13_cau_hinh_ca")
    if config_sheet:
        try:
            configs = config_sheet.get_all_records()
            for row in configs:
                print("CONFIG ROW:", row)
                thu = str(row.get("Thứ ", row.get("Thứ", ""))).strip()
                ca = str(row.get("Ca", "")).strip()
                status = str(row.get("Trạng thái", "")).strip().lower()

                if (
                    thu == day_names[day]
                    and ca == shift_names[shift]
                    and status == "active"
                ):
                    start_time = str(row.get("Giờ bắt đầu", "")).strip()
                    end_time = str(row.get("Giờ kết thúc", row.get("Giờ kết thúc ", row.get("Giờ kế thúc", row.get("Giờ kế thúc ", ""))))).strip()
                    location = str(row.get("Điểm bán", "TF Home")).strip() or "TF Home"
                    break
        except Exception:
            pass

    sheet = get_worksheet("12_lich_tuan")
    if not sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet 12_lich_tuan.")
        return

    
    existing_records = sheet.get_all_records()

    for idx, row in enumerate(existing_records):
        row_week = str(row.get("Tuần", row.get("Tuần ", ""))).strip()
        row_date = str(row.get("Ngày", row.get("Ngày ", ""))).strip()
        row_day = str(row.get("Thứ", row.get("Thứ ", ""))).strip()
        row_shift = str(row.get("Ca", row.get("Ca ", ""))).strip()
        row_staff = str(row.get("Nhân viên", row.get("Nhân viên ", ""))).strip()
        print("CHECK:", row_week, row_date, row_day, row_shift, row_staff)
        print("TARGET:", week_key, work_date, day_names[day], shift_names[shift], staff)

        
        if (
            row_week == week_key
            and row_date == work_date
            and row_day == day_names[day]
            and row_shift == shift_names[shift]
            and row_staff.lower() == staff.lower()
        ):
            await update.message.reply_text(
                f"⚠️ Ca này đã tồn tại:\n"
                f"{staff} - {day_names[day]} - Ca {shift_names[shift]}\n"
                f"Ngày: {work_date}"
            )
            return    
    sheet.append_row(
        
        [
            week_key,
            work_date,
            day_names[day],
            shift_names[shift],
            start_time,
            end_time,
            staff,
            location,
            "CONFIRMED",
            "",
        ],
        value_input_option="RAW",
        insert_data_option="INSERT_ROWS",
    )

    await update.message.reply_text(
        f"✅ Đã xếp ca:\n"
        f"{staff} - {day_names[day]} - Ca {shift_names[shift]}\n"
        f"Ngày: {work_date}\n"
        f"Giờ: {start_time} - {end_time}\n"
        f"Điểm bán: {location}"
    )
async def lich_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sheet = get_worksheet("12_lich_tuan")
    if not sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet 12_lich_tuan.")
        return

    try:
        records = sheet.get_all_records()
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc 12_lich_tuan:\n{e}")
        return

    if not records:
        await update.message.reply_text("📅 Chưa có lịch tuần.")
        return

    now_dt = datetime.now(TZ)
    week_key = now_dt.strftime("%Y-W%U")

    day_order = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
    shift_order = ["Sáng", "Tối"]

    grouped = {}

    for row in records:
        status = str(
            row.get("Trạng thái", row.get("Trạng thái ", ""))
        ).strip().upper()

        if status == "CANCELLED":
            continue
        row_week = str(row.get("Tuần", row.get("Tuần ", ""))).strip()
        if row_week != week_key:
            continue

        day = str(row.get("Thứ", row.get("Thứ ", ""))).strip()
        shift = str(row.get("Ca", row.get("Ca ", ""))).strip()
        staff = str(row.get("Nhân viên", row.get("Nhân viên ", ""))).strip()
        start_time = str(row.get("Giờ bắt đầu", row.get("Giờ bắt đầu ", ""))).strip()
        end_time = str(row.get("Giờ kết thúc", row.get("Giờ kết thúc ", ""))).strip()
        if not day or not shift or not staff:
            continue

        grouped.setdefault(day, {}).setdefault(shift, [])
        grouped[day][shift].append({
            "staff": staff,
            "start_time": start_time,
            "end_time": end_time,
        })

    if not grouped:
        await update.message.reply_text(f"📅 Chưa có lịch tuần {week_key}.")
        return

    lines = [f"📅 LỊCH TUẦN {week_key}", ""]

    for day in day_order:
        if day not in grouped:
            continue

        lines.append(f"{day}:")

        for shift in shift_order:
            shift_items = grouped.get(day, {}).get(shift, [])
            for item in shift_items:
                time_text = ""
                if item["start_time"] or item["end_time"]:
                    time_text = f" ({item['start_time']}-{item['end_time']})"

                lines.append(f"- Ca {shift}: {item['staff']}{time_text}")

        lines.append("")

    await update.message.reply_text("\n".join(lines))
async def xoaca_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args

    if len(args) < 3:
        await update.message.reply_text(
            "Cách dùng: /xoaca <ngày> <ca> <tên>\n"
            "Ví dụ: /xoaca t2 sang Huy"
        )
        return

    day = args[0].lower()
    shift = args[1].lower()
    staff = " ".join(args[2:]).strip()

    day_names = {
        "t2": "T2", "t3": "T3", "t4": "T4",
        "t5": "T5", "t6": "T6", "t7": "T7", "cn": "CN",
    }

    shift_names = {
        "sang": "Sáng",
        "toi": "Tối",
    }

    if day not in day_names:
        await update.message.reply_text("Ngày chưa đúng. Dùng: t2,t3,t4,t5,t6,t7,cn")
        return

    if shift not in shift_names:
        await update.message.reply_text("Ca chưa đúng. Dùng: sang hoặc toi")
        return

    now_dt = datetime.now(TZ)
    week_key = now_dt.strftime("%Y-W%U")

    sheet = get_worksheet("12_lich_tuan")
    if not sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet 12_lich_tuan.")
        return

    records = sheet.get_all_records()

    for idx, row in enumerate(records):
        row_index = idx + 2

        row_week = str(row.get("Tuần", row.get("Tuần ", ""))).strip()
        row_day = str(row.get("Thứ", row.get("Thứ ", ""))).strip()
        row_shift = str(row.get("Ca", row.get("Ca ", ""))).strip()
        row_staff = str(row.get("Nhân viên", row.get("Nhân viên ", ""))).strip()

        if (
            row_week == week_key
            and row_day == day_names[day]
            and row_shift == shift_names[shift]
            and row_staff.lower() == staff.lower()
        ):
            sheet.update(f"J{row_index}", [["CANCELLED"]], value_input_option="RAW")
            sheet.update(f"I{row_index}", [["Đã hủy ca"]], value_input_option="RAW")

            await update.message.reply_text(
                f"✅ Đã hủy ca:\n"
                f"{staff} - {day_names[day]} - Ca {shift_names[shift]}"
            )
            return

    await update.message.reply_text(
        f"⚠️ Không tìm thấy ca cần hủy:\n"
        f"{staff} - {day_names[day]} - Ca {shift_names[shift]}"
    )
async def tonggio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sheet = get_worksheet("12_lich_tuan")
    if not sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet 12_lich_tuan.")
        return

    records = sheet.get_all_records()

    now_dt = datetime.now(TZ)
    week_key = now_dt.strftime("%Y-W%U")

    totals = {}

    for row in records:
        row_week = str(row.get("Tuần", row.get("Tuần ", ""))).strip()
        if row_week != week_key:
            continue

        status = str(row.get("Trạng thái", row.get("Trạng thái ", ""))).strip().upper()
        if status == "CANCELLED":
            continue

        staff = str(row.get("Nhân viên", row.get("Nhân viên ", ""))).strip()
        start_time = str(row.get("Giờ bắt đầu", row.get("Giờ bắt đầu ", ""))).strip()
        end_time = str(row.get("Giờ kết thúc", row.get("Giờ kết thúc ", row.get("Giờ kế thúc", "")))).strip()
        print("TONGGIO:", staff, start_time, end_time)

        if not staff or not start_time or not end_time:
            continue

        try:
            start_dt = datetime.strptime(start_time, "%H:%M")
            end_dt = datetime.strptime(end_time, "%H:%M")
            hours = (end_dt - start_dt).seconds / 3600
        except Exception:
            continue

        totals[staff] = totals.get(staff, 0) + hours

    if not totals:
        await update.message.reply_text(f"📊 Chưa có dữ liệu giờ làm tuần {week_key}.")
        return

    lines = [f"📊 TỔNG GIỜ DỰ KIẾN TUẦN {week_key}", ""]

    for staff, hours in sorted(totals.items()):
        lines.append(f"- {staff}: {hours:g} giờ")

    await update.message.reply_text("\n".join(lines))
async def thieuca_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config_sheet = get_worksheet("13_cau_hinh_ca")
    lich_sheet = get_worksheet("12_lich_tuan")

    if not config_sheet or not lich_sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet xếp ca.")
        return

    configs = config_sheet.get_all_records()
    records = lich_sheet.get_all_records()

    now_dt = datetime.now(TZ)
    week_key = now_dt.strftime("%Y-W%U")

    scheduled = {}

    for row in records:
        row_week = str(row.get("Tuần", row.get("Tuần ", ""))).strip()
        if row_week != week_key:
            continue

        status = str(row.get("Trạng thái", row.get("Trạng thái ", ""))).strip().upper()
        if status == "CANCELLED":
            continue

        day = str(row.get("Thứ", row.get("Thứ ", ""))).strip()
        shift = str(row.get("Ca", row.get("Ca ", ""))).strip()
        staff = str(row.get("Nhân viên", row.get("Nhân viên ", ""))).strip()

        if not day or not shift or not staff:
            continue

        key = f"{day}|{shift}"
        scheduled[key] = scheduled.get(key, 0) + 1

    missing_lines = []

    for row in configs:
        status = str(row.get("Trạng thái", row.get("Trạng thái ", ""))).strip().lower()
        if status != "active":
            continue

        day = str(row.get("Thứ", row.get("Thứ ", ""))).strip()
        shift = str(row.get("Ca", row.get("Ca ", ""))).strip()
        need_text = str(row.get("Số người cần", row.get("Số người cần ", "0"))).strip()

        try:
            need = int(float(need_text))
        except Exception:
            need = 0

        key = f"{day}|{shift}"
        current = scheduled.get(key, 0)

        if current < need:
            missing_lines.append(
                f"- {day} Ca {shift}: cần {need}, đã xếp {current}, thiếu {need - current}"
            )

    if not missing_lines:
        await update.message.reply_text(f"✅ Tuần {week_key} đã đủ người theo cấu hình ca.")
        return

    lines = [f"⚠️ CẢNH BÁO THIẾU CA TUẦN {week_key}", ""]
    lines.extend(missing_lines)

    await update.message.reply_text("\n".join(lines)) 
async def canhan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args

    if len(args) < 1:
        await update.message.reply_text(
            "Cách dùng: /canhan <tên>\n"
            "Ví dụ: /canhan Huy"
        )
        return

    staff_query = " ".join(args).strip().lower()

    sheet = get_worksheet("12_lich_tuan")
    if not sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet 12_lich_tuan.")
        return

    records = sheet.get_all_records()

    now_dt = datetime.now(TZ)
    week_key = now_dt.strftime("%Y-W%U")

    day_order = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
    shift_order = ["Sáng", "Tối"]

    items = []
    total_hours = 0

    for row in records:
        row_week = str(row.get("Tuần", row.get("Tuần ", ""))).strip()
        if row_week != week_key:
            continue

        status = str(row.get("Trạng thái", row.get("Trạng thái ", ""))).strip().upper()
        if status == "CANCELLED":
            continue

        staff = str(row.get("Nhân viên", row.get("Nhân viên ", ""))).strip()
        if staff.lower() != staff_query:
            continue

        day = str(row.get("Thứ", row.get("Thứ ", ""))).strip()
        shift = str(row.get("Ca", row.get("Ca ", ""))).strip()
        start_time = str(row.get("Giờ bắt đầu", row.get("Giờ bắt đầu ", ""))).strip()
        end_time = str(row.get("Giờ kết thúc", row.get("Giờ kết thúc ", row.get("Giờ kế thúc", "")))).strip()

        try:
            start_dt = datetime.strptime(start_time, "%H:%M")
            end_dt = datetime.strptime(end_time, "%H:%M")
            hours = (end_dt - start_dt).seconds / 3600
        except Exception:
            hours = 0

        total_hours += hours

        items.append({
            "day": day,
            "shift": shift,
            "start": start_time,
            "end": end_time,
            "hours": hours,
            "staff": staff,
        })

    if not items:
        await update.message.reply_text(f"📅 Chưa có lịch của {staff_query.title()} tuần {week_key}.")
        return

    lines = [f"📅 LỊCH CÁ NHÂN TUẦN {week_key}", f"Nhân viên: {items[0]['staff']}", ""]

    for day in day_order:
        day_items = [x for x in items if x["day"] == day]
        if not day_items:
            continue

        lines.append(f"{day}:")
        for shift in shift_order:
            for item in day_items:
                if item["shift"] == shift:
                    lines.append(f"- Ca {shift}: {item['start']}-{item['end']} ({item['hours']:g} giờ)")
        lines.append("")

    lines.append(f"📊 Tổng giờ dự kiến: {total_hours:g} giờ")

    await update.message.reply_text("\n".join(lines))
async def canhdong_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sheet = get_worksheet("12_lich_tuan")
    if not sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet 12_lich_tuan.")
        return

    records = sheet.get_all_records()

    now_dt = datetime.now(TZ)
    week_key = now_dt.strftime("%Y-W%U")

    leaders = {}

    for row in records:
        row_week = str(row.get("Tuần", row.get("Tuần ", ""))).strip()
        if row_week != week_key:
            continue

        status = str(row.get("Trạng thái", row.get("Trạng thái ", ""))).strip().upper()
        if status == "CANCELLED":
            continue

        staff = str(row.get("Nhân viên", row.get("Nhân viên ", ""))).strip()
        start_time = str(row.get("Giờ bắt đầu", row.get("Giờ bắt đầu ", ""))).strip()
        end_time = str(row.get("Giờ kết thúc", row.get("Giờ kết thúc ", row.get("Giờ kế thúc", "")))).strip()

        if not staff or not start_time or not end_time:
            continue

        try:
            start_dt = datetime.strptime(start_time, "%H:%M")
            end_dt = datetime.strptime(end_time, "%H:%M")
            hours = (end_dt - start_dt).seconds / 3600
        except Exception:
            continue

        leaders[staff] = leaders.get(staff, 0) + hours

    if not leaders:
        await update.message.reply_text(f"📊 Chưa có dữ liệu cân đồng tuần {week_key}.")
        return

    sorted_staff = sorted(leaders.items(), key=lambda x: x[1], reverse=True)

    top_name, top_hours = sorted_staff[0]

    lines = [
        f"⚖️ CÂN ĐỒNG GIỜ LÀM TUẦN {week_key}",
        "",
        f"🏆 Đang cao nhất: {top_name} - {top_hours:g} giờ",
        "",
        "📋 Tổng giờ hiện tại:"
    ]

    for staff, hours in sorted_staff:
        lines.append(f"- {staff}: {hours:g} giờ")

    await update.message.reply_text("\n".join(lines))
async def doica_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args

        if len(args) < 4:
            await update.message.reply_text(
                "Cú pháp:\n/doica Ngày Ca Người_đổi Người_nhận"
            )
            return

        ngay = args[0]
        ca = args[1]
        nguoi_doi = args[2]
        nguoi_nhan = args[3]

        sheet = get_worksheet("15_doi_ca")

        records = sheet.get_all_records()

        new_id = len(records) + 1

        sheet.append_row([
            new_id,
            ngay,
            ca,
            nguoi_doi,
            nguoi_nhan,
            "PENDING",
            "",
            datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
        ])

        await update.message.reply_text(
            f"🔄 Yêu cầu đổi ca #{new_id}\n\n"
            f"📅 {ngay}\n"
            f"🕒 {ca}\n"
            f"👤 {nguoi_doi} → {nguoi_nhan}\n\n"
            f"⏳ Chờ Mr.Win duyệt"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
async def duyetca_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        args = context.args

        if len(args) < 1:
            await update.message.reply_text(
                "Cú pháp:\n/duyetca ID"
            )
            return

        request_id = int(args[0])

        sheet = get_worksheet("15_doi_ca")

        records = sheet.get_all_records()

        found = False

        for idx, row in enumerate(records, start=2):

            if int(row["ID"]) == request_id:

                sheet.update_cell(idx, 6, "APPROVED")
                sheet.update_cell(
                    idx,
                    7,
                    update.effective_user.first_name
                )

                found = True
                break

        if not found:
            await update.message.reply_text(
                "❌ Không tìm thấy yêu cầu."
            )
            return

        await update.message.reply_text(
            f"✅ Đã duyệt đổi ca #{request_id}"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
async def scanthieuca_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    sheet = get_worksheet("12_lich_tuan")

    if not sheet:
        await update.message.reply_text(
            "❌ Không kết nối được sheet 12_lich_tuan."
        )
        return

    rows = sheet.get_all_records()

    missing = []

    for row in rows:

        ngay = str(row.get("Ngày", "")).strip()
        ca = str(row.get("Ca", "")).strip()
        nv = str(row.get("Nhân viên", "")).strip()

        if not nv:
            missing.append((ngay, ca))

    if not missing:

        await update.message.reply_text(
            "✅ Không phát hiện ca thiếu."
        )
        return

    report = ["⚠️ CẢNH BÁO THIẾU CA\n"]

    warning_sheet = get_worksheet("16_thieu_ca")

    for ngay, ca in missing:

        report.append(f"📅 {ngay} | {ca}")

        if warning_sheet:
            warning_sheet.append_row([
                ngay,
                ca,
                "MISSING",
                datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
            ])

    await update.message.reply_text(
        "\n".join(report)
    )
async def chotlich_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sheet = get_worksheet("14_chot_lich")

    if not sheet:
        await update.message.reply_text(
            "❌ Không kết nối được sheet 14_chot_lich."
        )
        return

    now_dt = datetime.now(TZ)

    week_key = now_dt.strftime("%Y-W%U")

    user_name = update.effective_user.first_name

    sheet.append_row([
        week_key,
        "CLOSED",
        user_name,
        now_dt.strftime("%Y-%m-%d %H:%M")
    ])

    await update.message.reply_text(
        f"✅ ĐÃ CHỐT LỊCH TUẦN {week_key}\n\n"
        "Mọi thay đổi lịch phải được Mr.Win phê duyệt."
    )
async def nhanvien_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sheet = get_worksheet("00_Nhan_Vien")
    if not sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet 00_Nhan_Vien.")
        return

    records = sheet.get_all_records()

    names = []

    for row in records:
        name = str(row.get("Tên nhân viên", row.get("Tên nhân viên ", ""))).strip()
        status = str(row.get("Trạng thái", row.get("Trạng thái ", ""))).strip().lower()

        if not name:
            continue

        if status and status != "active":
            continue

        names.append(name)

    if not names:
        await update.message.reply_text("👥 Chưa có nhân viên active.")
        return

    lines = ["👥 DANH SÁCH NHÂN VIÊN ACTIVE", ""]

    for idx, name in enumerate(names, start=1):
        lines.append(f"{idx}. {name}")

    await update.message.reply_text("\n".join(lines))                   
async def week_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    shifts = DATA.get("shifts", {}).get(chat_id, {})

    if not shifts:
        await update.message.reply_text("Chưa có lịch ca. Dùng /shift để xếp lịch.")
        return

    day_order = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    day_names = {
        "mon": "T2",
        "tue": "T3",
        "wed": "T4",
        "thu": "T5",
        "fri": "T6",
        "sat": "T7",
        "sun": "CN",
    }

    lines = ["📅 LỊCH CA TUẦN NÀY", ""]

    for day in day_order:
        day_data = shifts.get(day, {})
        if not day_data:
            continue

        lines.append(f"{day_names[day]}:")

        if "sang" in day_data:
            lines.append(f"  Sáng: {day_data['sang']}")

        if "toi" in day_data:
            lines.append(f"  Tối: {day_data['toi']}")

        lines.append("")

    await update.message.reply_text("\n".join(lines))


async def clearshift_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)

    if "shifts" in DATA and chat_id in DATA["shifts"]:
        DATA["shifts"][chat_id] = {}
        save_data(DATA)

    await update.message.reply_text("✅ Đã xóa lịch ca tuần này.")    
async def todaywork_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    today_key = datetime.now(TZ).strftime("%Y-%m-%d")
    attendance = DATA.get("attendance", {}).get(chat_id, {}).get(today_key, {})

    if not attendance:
        await update.message.reply_text("📋 Hôm nay chưa có dữ liệu CHECKIN/CHECKOUT.")
        return

    lines = ["📋 CHẤM CÔNG HÔM NAY", ""]

    for staff_name, record in attendance.items():
        checkin = record.get("checkin", "Chưa có")
        checkout = record.get("checkout", "Chưa có")

        lines.append(f"{staff_name}")
        lines.append(f"- CHECKIN: {checkin}")
        lines.append(f"- CHECKOUT: {checkout}")
        lines.append("")

    await update.message.reply_text("\n".join(lines))
async def timesheet_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not gs_client:
        await update.message.reply_text("❌ Chưa kết nối Google Sheet.")
        return

    try:
        sheet = gs_client.open_by_key("1-2CUwuORi7L4HlUMx7n7uUVhMIFXL0_95PVp3_LGGe8").sheet1
        records = sheet.get_all_records()
        if not records:
            await update.message.reply_text("📋 Chưa có dữ liệu chấm công.")
            return

        lines = ["📋 BẢNG CHẤM CÔNG GẦN ĐÂY", ""]

        recent_records = records[-20:]


        for row in recent_records:
            ngay = row.get("Ngày", "")
            staff = row.get("Nhân viên", "")
            checkin = row.get("Checkin", "")
            checkout = row.get("Checkout", "")
            duration = row.get("Thời lượng", "")

            lines.append(f"📅 {ngay}")
            lines.append(f"👤 {staff}")
            lines.append(f"- CHECKIN: {checkin}")
            lines.append(f"- CHECKOUT: {checkout}")
            lines.append(f"- Thời lượng: {duration}")
            lines.append("")

        await update.message.reply_text("\n".join(lines))

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc Google Sheet:\n{e}")
async def staffadd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    staff_name = " ".join(context.args).strip().title()

    if not staff_name:
        await update.message.reply_text("❌ Cách dùng: /staffadd Tên nhân viên")
        return

    sheet = get_worksheet("00_Nhan_Vien")

    if not sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet 00_Nhan_Vien.")
        return

    rows = sheet.get_all_records()

    for row in rows:
        old_name = str(row.get("Tên nhân viên", "")).strip().title()
        status = str(row.get("Trạng thái", "")).strip().lower()

        if old_name == staff_name and status == "active":
            await update.message.reply_text(f"⚠️ {staff_name} đã có trong danh sách nhân viên.")
            return

    sheet.append_row([
        staff_name,
        "active",
        datetime.now(TZ).strftime("%d/%m/%Y"),
        ""
    ])

    await update.message.reply_text(f"✅ Đã thêm nhân viên: {staff_name}")
    
async def staffremove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    staff_name = " ".join(context.args).strip().title()

    if not staff_name:
        await update.message.reply_text("❌ Cách dùng: /staffremove Tên nhân viên")
        return

    sheet = get_worksheet("00_Nhan_Vien")

    if not sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet 00_Nhan_Vien.")
        return

    rows = sheet.get_all_records()

    for index, row in enumerate(rows, start=2):
        old_name = str(row.get("Tên nhân viên", "")).strip().title()

        if old_name == staff_name:
            sheet.update_cell(index, 2, "inactive")
            sheet.update_cell(index, 4, "Đã chuyển inactive")
            await update.message.reply_text(f"✅ Đã chuyển {staff_name} sang inactive.")
            return

    await update.message.reply_text(f"⚠️ Không tìm thấy nhân viên: {staff_name}")
async def revenue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text(
            "❌ Cách dùng:\n/revenue 3000000"
        )
        return

    try:
        amount = int(
            context.args[0]
            .replace(".", "")
            .replace(",", "")
        )
    except:
        await update.message.reply_text("❌ Số tiền không hợp lệ")
        return

    today = datetime.now(TZ).strftime("%d/%m/%Y")

    DATA.setdefault("revenue", {}).setdefault(chat_id, {})
    DATA["revenue"][chat_id][today] = amount

    save_data(DATA)
    try:
        sheet = get_worksheet("04_Doanh_Thu")
        if sheet:
            if sheet.row_values(1) != ["Ngày", "Doanh thu"]:
                sheet.insert_row(["Ngày", "Doanh thu"], 1)

            sheet.append_row([today, amount])
    
    except Exception as e:
        print("Google Sheet revenue error:", e)

    await update.message.reply_text(
        f"💰 Đã ghi nhận doanh thu {today}\n"
        f"{amount:,}đ".replace(",", ".")
    )
async def revenuelist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    revenue_data = DATA.get("revenue", {}).get(chat_id, {})

    if not revenue_data:
        await update.message.reply_text("❌ Chưa có dữ liệu doanh thu")
        return

    lines = ["💰 DOANH THU TF", ""]
    total = 0

    for day, amount in sorted(revenue_data.items()):
        total += amount
        lines.append(f"{day}: {amount:,}đ".replace(",", "."))

    lines.append("")
    lines.append(f"🏦 Tổng doanh thu: {total:,}đ".replace(",", "."))

    await update.message.reply_text("\n".join(lines))
async def income_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = str(update.effective_chat.id)

    if len(context.args) < 2:
        await update.message.reply_text(
            "Cách dùng:\n/income TF 120"
        )
        return

    source = context.args[0].upper()

    try:
        amount = float(context.args[1])
    except:
        await update.message.reply_text("Số tiền không hợp lệ")
        return

    DATA.setdefault("income", {}).setdefault(chat_id, {})

    DATA["income"][chat_id][source] = amount

    save_data(DATA)

    await update.message.reply_text(
        f"✅ Đã cập nhật\n{source}: {amount}tr"
    )
async def incomelist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = str(update.effective_chat.id)

    income_data = DATA.get("income", {}).get(chat_id, {})

    if not income_data:
        await update.message.reply_text(
            "Chưa có nguồn thu nào."
        )
        return

    total = 0
    lines = ["📊 TỔNG THU NHẬP", ""]

    for source, amount in sorted(income_data.items()):
        total += amount
        lines.append(f"{source}: {amount}tr")

    lines.append("")
    lines.append(f"💰 Tổng: {total}tr")

    await update.message.reply_text(
        "\n".join(lines)
    )
async def revenueweek_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    revenue_data = DATA.get("revenue", {}).get(chat_id, {})

    if not revenue_data:
        await update.message.reply_text("❌ Chưa có dữ liệu doanh thu")
        return

    today = datetime.now(TZ).date()
    start_week = today - timedelta(days=today.weekday())
    end_week = start_week + timedelta(days=6)

    lines = ["📊 DOANH THU TUẦN TF", ""]
    total = 0

    for day_text, amount in sorted(revenue_data.items()):
        try:
            day_obj = datetime.strptime(day_text, "%d/%m/%Y").date()
        except:
            continue

        if start_week <= day_obj <= end_week:
            total += amount
            lines.append(f"{day_text}: {amount:,}đ".replace(",", "."))

    if total == 0:
        await update.message.reply_text("❌ Tuần này chưa có doanh thu")
        return

    lines.append("")
    lines.append(f"🏦 Tổng doanh thu tuần: {total:,}đ".replace(",", "."))

    await update.message.reply_text("\n".join(lines))
async def revenuemonth_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    revenue_data = DATA.get("revenue", {}).get(chat_id, {})

    if not revenue_data:
        await update.message.reply_text("❌ Chưa có dữ liệu doanh thu")
        return

    now_dt = datetime.now(TZ)
    current_month = now_dt.strftime("%m")
    current_year = now_dt.strftime("%Y")

    lines = [f"📈 DOANH THU THÁNG TF {current_month}/{current_year}", ""]
    total = 0
    count_days = 0

    for day_text, amount in sorted(revenue_data.items()):
        try:
            day_obj = datetime.strptime(day_text, "%d/%m/%Y")
        except:
            continue

        if day_obj.strftime("%m") == current_month and day_obj.strftime("%Y") == current_year:
            total += amount
            count_days += 1
            lines.append(f"{day_text}: {amount:,}đ".replace(",", "."))

    if total == 0:
        await update.message.reply_text("❌ Tháng này chưa có doanh thu")
        return

    average = round(total / count_days) if count_days else 0

    lines.append("")
    lines.append("------------------")
    lines.append(f"🏦 Tổng doanh thu tháng: {total:,}đ".replace(",", "."))
    lines.append(f"📅 Số ngày có doanh thu: {count_days}")
    lines.append(f"📊 Trung bình/ngày: {average:,}đ".replace(",", "."))

    await update.message.reply_text("\n".join(lines))
async def revenuedashboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    revenue_data = DATA.get("revenue", {}).get(chat_id, {})

    if not revenue_data:
        await update.message.reply_text("❌ Chưa có dữ liệu doanh thu")
        return

    today = datetime.now(TZ).date()
    start_week = today - timedelta(days=today.weekday())

    today_text = today.strftime("%d/%m/%Y")
    current_month = today.strftime("%m")
    current_year = today.strftime("%Y")

    today_total = 0
    week_total = 0
    month_total = 0
    month_days = 0

    best_day = ""
    best_amount = 0

    for day_text, amount in revenue_data.items():
        try:
            day_obj = datetime.strptime(day_text, "%d/%m/%Y").date()
        except:
            continue

        if day_text == today_text:
            today_total += amount

        if start_week <= day_obj <= today:
            week_total += amount

        if day_obj.strftime("%m") == current_month and day_obj.strftime("%Y") == current_year:
            month_total += amount
            month_days += 1

        if amount > best_amount:
            best_amount = amount
            best_day = day_text

    average = round(month_total / month_days) if month_days else 0

    await update.message.reply_text(
        "📊 DASHBOARD DOANH THU TF\n\n"
        f"💰 Hôm nay: {today_total:,}đ\n"
        f"📅 Tuần này: {week_total:,}đ\n"
        f"📈 Tháng này: {month_total:,}đ\n"
        f"📊 Trung bình/ngày: {average:,}đ\n\n"
        f"🔥 Ngày cao nhất: {best_day}\n"
        f"{best_amount:,}đ"
        .replace(",", ".")
    ) 
async def expense_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Cách dùng:\n/expense 250000 cà phê hạt"
        )
        return

    try:
        amount = int(
            context.args[0]
            .replace(".", "")
            .replace(",", "")
        )
    except:
        await update.message.reply_text("❌ Số tiền không hợp lệ")
        return

    note = " ".join(context.args[1:]).strip()
    today = datetime.now(TZ).strftime("%d/%m/%Y")

    DATA.setdefault("expense", {}).setdefault(chat_id, {})
    DATA["expense"][chat_id].setdefault(today, [])

    DATA["expense"][chat_id][today].append({
        "amount": amount,
        "note": note
    })

    save_data(DATA)
    try:
        sheet = get_worksheet("05_Chi_Phi")
        if sheet:
            sheet.append_row([today, note, amount])
    except Exception as e:
        print("Google Sheet expense error:", e)

    await update.message.reply_text(
        f"💸 Đã ghi chi phí {today}\n"
        f"- {note}: {amount:,}đ".replace(",", ".")
    )
async def expenselist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    expense_data = DATA.get("expense", {}).get(chat_id, {})

    if not expense_data:
        await update.message.reply_text("❌ Chưa có dữ liệu chi phí")
        return

    lines = ["💸 CHI PHÍ TF", ""]
    total = 0

    for day_text, items in sorted(expense_data.items()):
        lines.append(f"📅 {day_text}")

        for item in items:
            amount = item.get("amount", 0)
            note = item.get("note", "")
            total += amount
            lines.append(f"- {note}: {amount:,}đ".replace(",", "."))

        lines.append("")

    lines.append("------------------")
    lines.append(f"🏦 Tổng chi phí: {total:,}đ".replace(",", "."))

    await update.message.reply_text("\n".join(lines))
async def resetfinance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if not context.args or " ".join(context.args).strip().upper() != "CONFIRM":
        await update.message.reply_text(
            "⚠️ Lệnh này sẽ xoá toàn bộ dữ liệu Doanh thu, Chi phí, P/L của nhóm này.\n\n"
            "Để xác nhận, gõ:\n"
            "/resetfinance CONFIRM"
        )
        return

    DATA.setdefault("revenue", {})[chat_id] = {}
    DATA.setdefault("expense", {})[chat_id] = {}
    save_data(DATA)

    try:
        sheets = {
            "04_Doanh_Thu": ["Ngày", "Doanh thu"],
            "05_Chi_Phi": ["Ngày", "Loại chi phí", "Số tiền"],
            "06_P_L": ["Ngày", "Doanh thu", "Chi phí", "Lợi nhuận"],
        }

        for sheet_name, header in sheets.items():
            sheet = get_worksheet(sheet_name)
            if sheet:
                sheet.clear()
                sheet.append_row(header)

    except Exception as e:
        print("Google Sheet reset finance error:", e)

    await update.message.reply_text(
        "✅ Đã xoá dữ liệu tài chính của nhóm này.\n"
        "Đã reset Doanh thu, Chi phí, P/L và giữ lại tiêu đề Google Sheet."
    )
async def pl_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(TZ).strftime("%d/%m/%Y")

    revenue_today = 0
    expense_total = 0

    try:
        revenue_ws = get_worksheet("04_Doanh_Thu")
        revenue_rows = revenue_ws.get_all_records()

        for row in revenue_rows:
            if str(row.get("Ngày", "")).strip() == today:
                amount = str(row.get("Doanh thu", "0")).replace(".", "").replace(",", "").strip()
                revenue_today = int(amount) if amount else 0
                break
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc sheet doanh thu: {e}")
        return

    try:
        expense_ws = get_worksheet("05_Chi_Phi")
        expense_rows = expense_ws.get_all_records()

        for row in expense_rows:
            if str(row.get("Ngày", "")).strip() == today:
                amount = str(row.get("Số tiền", "0")).replace(".", "").replace(",", "").strip()
                expense_total += int(amount) if amount else 0
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc sheet chi phí: {e}")
        return

    profit = revenue_today - expense_total

    lines = [
        f"📊 P/L TF {today}",
        "",
        f"💰 Doanh thu: {revenue_today:,}đ".replace(",", "."),
        f"💸 Chi phí: {expense_total:,}đ".replace(",", "."),
        "----------------",
        f"🏆 Lợi nhuận: {profit:,}đ".replace(",", "."),
    ]

    try:
        sheet = get_worksheet("06_P_L")
        if sheet:
            if sheet.row_values(1) != ["Ngày", "Doanh thu", "Chi phí", "Lợi nhuận"]:
                sheet.insert_row(["Ngày", "Doanh thu", "Chi phí", "Lợi nhuận"], 1)

            records = sheet.get_all_values()
            target_row = None

            for i, row in enumerate(records[1:], start=2):
                if row and row[0] == today:
                    target_row = i
                    break

            if target_row:
                sheet.update(f"A{target_row}:D{target_row}", [[today, revenue_today, expense_total, profit]])
            else:
                sheet.append_row([today, revenue_today, expense_total, profit])
    except Exception as e:
        print("Google Sheet P/L error:", e)

    await update.message.reply_text("\n".join(lines))
async def financeweek_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today_dt = datetime.now(TZ)
    start_dt = today_dt - timedelta(days=today_dt.weekday())
    end_dt = start_dt + timedelta(days=6)

    total_revenue = 0
    total_expense = 0

    try:
        revenue_ws = get_worksheet("04_Doanh_Thu")
        revenue_rows = revenue_ws.get_all_records()

        for row in revenue_rows:
            row_date = str(row.get("Ngày", "")).strip()
            if not row_date:
                continue

            try:
                row_dt = datetime.strptime(row_date, "%d/%m/%Y").replace(tzinfo=TZ)
            except Exception:
                continue

            if start_dt.date() <= row_dt.date() <= end_dt.date():
                amount = str(row.get("Doanh thu", "0")).replace(".", "").replace(",", "").strip()
                total_revenue += int(amount) if amount else 0

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc sheet doanh thu: {e}")
        return

    try:
        expense_ws = get_worksheet("05_Chi_Phi")
        expense_rows = expense_ws.get_all_records()

        for row in expense_rows:
            row_date = str(row.get("Ngày", "")).strip()
            if not row_date:
                continue

            try:
                row_dt = datetime.strptime(row_date, "%d/%m/%Y").replace(tzinfo=TZ)
            except Exception:
                continue

            if start_dt.date() <= row_dt.date() <= end_dt.date():
                amount = str(row.get("Số tiền", "0")).replace(".", "").replace(",", "").strip()
                total_expense += int(amount) if amount else 0

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc sheet chi phí: {e}")
        return

    profit = total_revenue - total_expense

    await update.message.reply_text(
        f"📊 P/L TUẦN TF\n"
        f"Từ {start_dt.strftime('%d/%m/%Y')} đến {end_dt.strftime('%d/%m/%Y')}\n\n"
        f"💰 Doanh thu: {total_revenue:,}đ".replace(",", ".") + "\n"
        f"💸 Chi phí: {total_expense:,}đ".replace(",", ".") + "\n"
        "────────────────\n"
        f"🏆 Lợi nhuận: {profit:,}đ".replace(",", ".")
    )


async def financemonth_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today_dt = datetime.now(TZ)
    current_month = today_dt.month
    current_year = today_dt.year

    total_revenue = 0
    total_expense = 0

    try:
        revenue_ws = get_worksheet("04_Doanh_Thu")
        revenue_rows = revenue_ws.get_all_records()

        for row in revenue_rows:
            row_date = str(row.get("Ngày", "")).strip()
            if not row_date:
                continue

            try:
                row_dt = datetime.strptime(row_date, "%d/%m/%Y").replace(tzinfo=TZ)
            except Exception:
                continue

            if row_dt.month == current_month and row_dt.year == current_year:
                amount = str(row.get("Doanh thu", "0")).replace(".", "").replace(",", "").strip()
                total_revenue += int(amount) if amount else 0

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc sheet doanh thu: {e}")
        return

    try:
        expense_ws = get_worksheet("05_Chi_Phi")
        expense_rows = expense_ws.get_all_records()

        for row in expense_rows:
            row_date = str(row.get("Ngày", "")).strip()
            if not row_date:
                continue

            try:
                row_dt = datetime.strptime(row_date, "%d/%m/%Y").replace(tzinfo=TZ)
            except Exception:
                continue

            if row_dt.month == current_month and row_dt.year == current_year:
                amount = str(row.get("Số tiền", "0")).replace(".", "").replace(",", "").strip()
                total_expense += int(amount) if amount else 0

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc sheet chi phí: {e}")
        return

    profit = total_revenue - total_expense

    await update.message.reply_text(
        f"📊 P/L THÁNG TF\n"
        f"Tháng {today_dt.strftime('%m/%Y')}\n\n"
        f"💰 Doanh thu: {total_revenue:,}đ".replace(",", ".") + "\n"
        f"💸 Chi phí: {total_expense:,}đ".replace(",", ".") + "\n"
        "────────────────\n"
        f"🏆 Lợi nhuận: {profit:,}đ".replace(",", ".")
    )    
async def plmonth_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    revenue_data = DATA.get("revenue", {}).get(chat_id, {})
    expense_data = DATA.get("expense", {}).get(chat_id, {})

    current_month = datetime.now(TZ).strftime("%m")
    current_year = datetime.now(TZ).strftime("%Y")

    revenue_total = 0
    expense_total = 0

    for day_text, amount in revenue_data.items():
        try:
            day_obj = datetime.strptime(day_text, "%d/%m/%Y")
        except:
            continue

        if (
            day_obj.strftime("%m") == current_month
            and day_obj.strftime("%Y") == current_year
        ):
            revenue_total += amount

    for day_text, items in expense_data.items():
        try:
            day_obj = datetime.strptime(day_text, "%d/%m/%Y")
        except:
            continue

        if (
            day_obj.strftime("%m") == current_month
            and day_obj.strftime("%Y") == current_year
        ):
            for item in items:
                expense_total += item.get("amount", 0)

    profit = revenue_total - expense_total

    lines = [
        f"📊 P/L THÁNG {current_month}/{current_year}",
        "",
        f"💰 Doanh thu: {revenue_total:,}đ".replace(",", "."),
        f"💸 Chi phí: {expense_total:,}đ".replace(",", "."),
        "------------------",
        f"🏆 Lợi nhuận: {profit:,}đ".replace(",", "."),
    ]

    await update.message.reply_text("\n".join(lines))                           

async def paymentrequest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text(
            "Cú pháp:\n/paymentrequest LOAI_CHI_PHI SO_TIEN NOI_DUNG\n"
            "Ví dụ: /paymentrequest KHO 1500000 Nhập hàng sữa"
        )
        return

    expense_type = context.args[0].strip().upper()
    if not expense_type:
        await update.message.reply_text("❌ Loại chi phí không được rỗng.")
        return

    try:
        amount = parse_positive_amount(context.args[1])
    except Exception:
        await update.message.reply_text("❌ Số tiền phải là số dương.")
        return

    content = " ".join(context.args[2:]).strip()
    if not content:
        await update.message.reply_text("❌ Nội dung không được rỗng.")
        return

    try:
        ws = get_payment_worksheet()
        if not ws:
            await update.message.reply_text("❌ Chưa kết nối Google Sheet.")
            return

        rows = ws.get_all_values()
        request_id = next_payment_id(rows)
        request_date = datetime.now(TZ).strftime("%d/%m/%Y")
        requester = telegram_user_name(update)

        ws.append_row(
            [
                request_id,
                request_date,
                requester,
                expense_type,
                content,
                amount,
                PAYMENT_STATUS_PENDING,
                "",
                "",
                "",
                "",
                "",
            ],
            value_input_option="RAW",
            insert_data_option="INSERT_ROWS",
        )

        await update.message.reply_text(
            f"✅ Đã tạo đề nghị thanh toán {request_id}\n"
            f"🧾 Loại chi phí: {expense_type}\n"
            f"📝 Nội dung: {content}\n"
            f"💰 Số tiền: {format_vnd(amount)}\n"
            f"📌 Trạng thái: {payment_status_text(PAYMENT_STATUS_PENDING)}"
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"⏳ Có đề nghị thanh toán mới cần duyệt: {request_id}",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi tạo đề nghị thanh toán: {e}")


async def paymentlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ws = get_payment_worksheet()
        if not ws:
            await update.message.reply_text("❌ Chưa kết nối Google Sheet.")
            return

        rows = ws.get_all_values()
        records = [payment_row_to_dict(row) for row in rows[1:] if row]
        records = records[-10:]

        if not records:
            await update.message.reply_text("📋 Chưa có đề nghị thanh toán.")
            return

        await update.message.reply_text(
            build_payment_lines(records, "📋 ĐỀ NGHỊ THANH TOÁN GẦN NHẤT")
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc đề nghị thanh toán: {e}")


async def paymentdetail_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Cú pháp:\n/paymentdetail ID\nVí dụ: /paymentdetail DN001")
        return

    request_id = context.args[0].strip().upper()
    try:
        ws = get_payment_worksheet()
        if not ws:
            await update.message.reply_text("❌ Chưa kết nối Google Sheet.")
            return

        _row_index, record = find_payment_row(ws, request_id)
        if not record:
            await update.message.reply_text(f"❌ Không tìm thấy đề nghị {request_id}.")
            return

        await update.message.reply_text(build_payment_detail(record))
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc chi tiết đề nghị thanh toán: {e}")


async def paymentpending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ws = get_payment_worksheet()
        if not ws:
            await update.message.reply_text("❌ Chưa kết nối Google Sheet.")
            return

        rows = ws.get_all_values()
        records = [
            payment_row_to_dict(row)
            for row in rows[1:]
            if row and payment_row_to_dict(row).get("Trạng thái") == PAYMENT_STATUS_PENDING
        ]

        if not records:
            await update.message.reply_text("✅ Không có đề nghị đang chờ duyệt.")
            return

        await update.message.reply_text(
            build_payment_lines(records[-20:], "⏳ ĐỀ NGHỊ ĐANG CHỜ DUYỆT")
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc đề nghị chờ duyệt: {e}")


async def paymentapprove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not can_approve_payment(update):
        await update.message.reply_text(PAYMENT_PERMISSION_DENIED)
        return

    if len(context.args) < 1:
        await update.message.reply_text("Cú pháp:\n/paymentapprove ID\nVí dụ: /paymentapprove DN001")
        return

    request_id = context.args[0].strip().upper()
    try:
        ws = get_payment_worksheet()
        if not ws:
            await update.message.reply_text("❌ Chưa kết nối Google Sheet.")
            return

        row_index, record = find_payment_row(ws, request_id)
        if not record:
            await update.message.reply_text(f"❌ Không tìm thấy đề nghị {request_id}.")
            return

        current_status = str(record.get("Trạng thái", "")).strip()
        if current_status != PAYMENT_STATUS_PENDING:
            await update.message.reply_text(
                f"❌ Không thể duyệt {request_id} vì trạng thái hiện tại là {current_status}.\n"
                f"Chỉ duyệt được đề nghị {PAYMENT_STATUS_PENDING}."
            )
            return

        approver = telegram_user_name(update)
        approve_date = datetime.now(TZ).strftime("%d/%m/%Y")
        ws.update(f"G{row_index}:I{row_index}", [[PAYMENT_STATUS_APPROVED, approver, approve_date]], value_input_option="RAW")

        await update.message.reply_text(
            f"✅ Đề nghị {request_id} đã được duyệt.\n"
            f"👤 Người duyệt: {approver}\n"
            f"📅 Ngày duyệt: {approve_date}"
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ Đề nghị thanh toán {request_id} đã được duyệt bởi {approver}.",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi duyệt đề nghị thanh toán: {e}")


async def paymentreject_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not can_approve_payment(update):
        await update.message.reply_text(PAYMENT_PERMISSION_DENIED)
        return

    if len(context.args) < 2:
        await update.message.reply_text("Cú pháp:\n/paymentreject ID Lý_do\nVí dụ: /paymentreject DN001 Thiếu hóa đơn")
        return

    request_id = context.args[0].strip().upper()
    reject_reason = " ".join(context.args[1:]).strip()
    if not reject_reason:
        await update.message.reply_text("❌ Lý do từ chối không được rỗng.")
        return

    try:
        ws = get_payment_worksheet()
        if not ws:
            await update.message.reply_text("❌ Chưa kết nối Google Sheet.")
            return

        row_index, record = find_payment_row(ws, request_id)
        if not record:
            await update.message.reply_text(f"❌ Không tìm thấy đề nghị {request_id}.")
            return

        current_status = str(record.get("Trạng thái", "")).strip()
        if current_status != PAYMENT_STATUS_PENDING:
            await update.message.reply_text(
                f"❌ Không thể từ chối {request_id} vì trạng thái hiện tại là {current_status}.\n"
                f"Chỉ từ chối được đề nghị {PAYMENT_STATUS_PENDING}."
            )
            return

        approver = telegram_user_name(update)
        reject_date = datetime.now(TZ).strftime("%d/%m/%Y")
        ws.update(f"G{row_index}:I{row_index}", [[PAYMENT_STATUS_REJECTED, approver, reject_date]], value_input_option="RAW")
        ws.update(f"L{row_index}", [[reject_reason]], value_input_option="RAW")

        await update.message.reply_text(
            f"❌ Đề nghị {request_id} đã bị từ chối.\n"
            f"👤 Người duyệt: {approver}\n"
            f"📅 Ngày duyệt: {reject_date}\n"
            f"🗒 Lý do: {reject_reason}"
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ Đề nghị thanh toán {request_id} đã bị từ chối bởi {approver}.\n🗒 Lý do: {reject_reason}",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi từ chối đề nghị thanh toán: {e}")


async def paymentpaid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not can_pay_payment(update):
        await update.message.reply_text(PAYMENT_PERMISSION_DENIED)
        return

    if len(context.args) < 1:
        await update.message.reply_text("Cú pháp:\n/paymentpaid ID\nVí dụ: /paymentpaid DN001")
        return

    request_id = context.args[0].strip().upper()
    try:
        ws = get_payment_worksheet()
        if not ws:
            await update.message.reply_text("❌ Chưa kết nối Google Sheet.")
            return

        row_index, record = find_payment_row(ws, request_id)
        if not record:
            await update.message.reply_text(f"❌ Không tìm thấy đề nghị {request_id}.")
            return

        current_status = str(record.get("Trạng thái", "")).strip()
        if current_status != PAYMENT_STATUS_APPROVED:
            await update.message.reply_text(
                f"❌ Không thể thanh toán {request_id} vì trạng thái hiện tại là {current_status}.\n"
                f"Chỉ thanh toán được đề nghị {PAYMENT_STATUS_APPROVED}."
            )
            return

        payer = telegram_user_name(update)
        paid_date = datetime.now(TZ).strftime("%d/%m/%Y")
        ws.update(f"G{row_index}:K{row_index}", [[PAYMENT_STATUS_PAID, record.get("Người duyệt", ""), record.get("Ngày duyệt", ""), payer, paid_date]], value_input_option="RAW")

        await update.message.reply_text(
            f"💸 Đề nghị {request_id} đã được thanh toán.\n"
            f"👤 Người thanh toán: {payer}\n"
            f"📅 Ngày thanh toán: {paid_date}"
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"💸 Đề nghị thanh toán {request_id} đã được thanh toán bởi {payer}.",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đánh dấu thanh toán: {e}")


async def paymentreport_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not can_view_payment_report(update):
        await update.message.reply_text(PAYMENT_PERMISSION_DENIED)
        return

    if len(context.args) < 1 or context.args[0].lower() not in ("week", "month"):
        await update.message.reply_text(
            "Cú pháp:\n/paymentreport week\n/paymentreport month"
        )
        return

    report_type = context.args[0].lower()
    now_dt = datetime.now(TZ)
    if report_type == "week":
        start_date = (now_dt - timedelta(days=now_dt.weekday())).date()
        end_date = start_date + timedelta(days=6)
        title = f"📊 BÁO CÁO ĐỀ NGHỊ THANH TOÁN TUẦN\n{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}"
    else:
        start_date = now_dt.replace(day=1).date()
        if now_dt.month == 12:
            next_month = now_dt.replace(year=now_dt.year + 1, month=1, day=1)
        else:
            next_month = now_dt.replace(month=now_dt.month + 1, day=1)
        end_date = (next_month - timedelta(days=1)).date()
        title = f"📊 BÁO CÁO ĐỀ NGHỊ THANH TOÁN THÁNG {now_dt.strftime('%m/%Y')}"

    try:
        ws = get_payment_worksheet()
        if not ws:
            await update.message.reply_text("❌ Chưa kết nối Google Sheet.")
            return

        rows = ws.get_all_values()
        records = []
        for row in rows[1:]:
            if not row:
                continue
            record = payment_row_to_dict(row)
            request_date = parse_payment_date(record.get("Ngày đề nghị", ""))
            if not request_date:
                continue
            if start_date <= request_date.date() <= end_date:
                records.append(record)

        counts = {
            PAYMENT_STATUS_PENDING: 0,
            PAYMENT_STATUS_APPROVED: 0,
            PAYMENT_STATUS_REJECTED: 0,
            PAYMENT_STATUS_PAID: 0,
        }
        paid_total = 0

        for record in records:
            status = str(record.get("Trạng thái", "")).strip()
            if status in counts:
                counts[status] += 1
            if status == PAYMENT_STATUS_PAID:
                try:
                    paid_total += int(str(record.get("Số tiền", "0")).replace(".", "").replace(",", "").strip() or 0)
                except Exception:
                    pass

        approved_total = counts[PAYMENT_STATUS_APPROVED] + counts[PAYMENT_STATUS_PAID]

        lines = [
            title,
            "",
            f"Tổng số đề nghị: {len(records)}",
            f"⏳ Đang chờ duyệt: {counts[PAYMENT_STATUS_PENDING]}",
            f"✅ Đã duyệt: {approved_total}",
            f"❌ Đã từ chối: {counts[PAYMENT_STATUS_REJECTED]}",
            f"💸 Đã thanh toán: {counts[PAYMENT_STATUS_PAID]}",
            f"Tổng tiền đã thanh toán: {format_vnd(paid_total)}",
        ]
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi báo cáo đề nghị thanh toán: {e}")

async def stafflist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sheet = get_worksheet("00_Nhan_Vien")

    if not sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet 00_Nhan_Vien.")
        return

    rows = sheet.get_all_records()

    active_staff = []
    inactive_staff = []

    for row in rows:
        name = str(row.get("Tên nhân viên", "")).strip()
        status = str(row.get("Trạng thái", "")).strip().lower()

        if not name:
            continue

        if status == "active":
            active_staff.append(name)
        else:
            inactive_staff.append(name)

    if not active_staff:
        await update.message.reply_text("📋 Chưa có nhân viên active nào.")
        return

    lines = ["📋 DANH SÁCH NHÂN VIÊN ĐANG LÀM TF", ""]

    for index, name in enumerate(active_staff, start=1):
        lines.append(f"{index}. {name}")

    await update.message.reply_text("\n".join(lines))  
   
async def checkshift_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    day_keys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    day_names = {
        "mon": "T2",
        "tue": "T3",
        "wed": "T4",
        "thu": "T5",
        "fri": "T6",
        "sat": "T7",
        "sun": "CN",
    }
    shift_names = {
        "sang": "Sáng",
        "toi": "Tối",
    }

    today_key = day_keys[datetime.now(TZ).weekday()]
    today_text = day_names.get(today_key, today_key)

    shift_group_id = DATA.get("settings", {}).get(chat_id, {}).get("shift_group_id", chat_id)
    today_shifts = DATA.get("shifts", {}).get(shift_group_id, {}).get(today_key, {})
    linked_note = "" if shift_group_id == chat_id else f"\n🔗 Lịch ca lấy từ nhóm: {shift_group_id}"
    today_attendance = DATA.get("attendance", {}).get(chat_id, {}).get(
        datetime.now(TZ).strftime("%Y-%m-%d"), {}
    )

    lines = [f"📋 KIỂM TRA LỊCH CA HÔM NAY ({today_text}){linked_note}", ""]

    lines.append("🗓 Lịch ca hôm nay:")
    if today_shifts:
        scheduled_names = []
        for shift_key, staff_name in today_shifts.items():
            shift_text = shift_names.get(shift_key, shift_key)
            lines.append(f"- {shift_text}: {staff_name}")
            scheduled_names.append(staff_name.strip())
    else:
        scheduled_names = []
        lines.append("- Chưa có lịch ca hôm nay.")

    lines.append("")
    lines.append("🕒 Chấm công hôm nay:")
    if today_attendance:
        attendance_names = []
        for staff_name, record in today_attendance.items():
            checkin = record.get("checkin", "Chưa có")
            checkout = record.get("checkout", "Chưa có")
            lines.append(f"- {staff_name}: CHECKIN {checkin} / CHECKOUT {checkout}")
            attendance_names.append(staff_name.strip())
    else:
        attendance_names = []
        lines.append("- Chưa có dữ liệu chấm công hôm nay.")

    warnings = []
    for staff_name in attendance_names:
        if staff_name not in scheduled_names:
            warnings.append(f"- {staff_name} có chấm công nhưng chưa có trong lịch ca hôm nay.")

    lines.append("")
    lines.append("⚠️ Cảnh báo:")
    if warnings:
        lines.extend(warnings)
    else:
        lines.append("- Chưa phát hiện lệch lịch ca.")

    await update.message.reply_text("\n".join(lines))
async def getchatid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    title = update.effective_chat.title or "Chat cá nhân"

    await update.message.reply_text(
        f"🆔 CHAT ID\n"
        f"Nhóm/Chat: {title}\n"
        f"ID: {chat_id}"
    )
async def linkshiftgroup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text(
            "Cách dùng: /linkshiftgroup <chat_id_nhóm_xếp_ca>\n"
            "Ví dụ: /linkshiftgroup -5215186149"
        )
        return

    shift_group_id = context.args[0].strip()

    DATA.setdefault("settings", {}).setdefault(chat_id, {})
    DATA["settings"][chat_id]["shift_group_id"] = shift_group_id
    save_data(DATA)

    await update.message.reply_text(
        f"✅ Đã liên kết nhóm xếp ca:\n"
        f"{shift_group_id}\n\n"
        f"Từ nay /checkshift ở nhóm này sẽ lấy lịch ca từ nhóm xếp ca đã liên kết."
    )
async def payrollweek_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("PAYROLLWEEK RUNNING")
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)

    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("⛔ Chỉ admin mới được xem bảng lương.")
        return
    rate = 30000
    chat_id = str(update.effective_chat.id)
    now_ts = datetime.now(TZ).timestamp()

    last_run = PAYROLL_LOCK.get(chat_id, 0)

    if now_ts - last_run < 5:
        await update.message.reply_text("⏳ Vui lòng chờ vài giây rồi bấm lại /payrollweek.")
        return
    PAYROLL_LOCK[chat_id] = now_ts
    try:
        spreadsheet = gs_client.open_by_key("1-2CUwuORi7L4HlUMx7n7uUVhMIFXL0_95PVp3_LGGe8")
        sheet = spreadsheet.worksheet("01_Cham_Cong")
        records = sheet.get_all_records()

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc Google Sheet:\n{e}")
        return
    totals = {}
    issues = set()
    lines = [f"💰 BẢNG LƯƠNG TẠM TUẦN NÀY", ""]



    recent_records = records[-50:]

    for row in recent_records:

        staff_name = row.get("Nhân viên", "")
        checkin = row.get("Checkin", "")
        checkout = row.get("Checkout", "")
        duration_text = row.get("Thời lượng", "")
        if not staff_name:
            continue
        if not checkin or not checkout:
            continue
        if not duration_text:
            continue



        try:
            minutes = 0
            duration_text = str(duration_text).lower().strip()

            if "giờ" in duration_text:
                parts = duration_text.split("giờ")
                hours = int(parts[0].strip())

                mins = 0
                if len(parts) > 1 and "phút" in parts[1]:
                    mins_text = parts[1].replace("phút", "").strip()
                    mins = int(mins_text) if mins_text else 0

                minutes = hours * 60 + mins

            elif "phút" in duration_text:
                minutes = int(duration_text.replace("phút", "").strip())

            else:
                raise Exception("invalid duration")

            if minutes <= 0:
                continue

            totals.setdefault(staff_name, 0)
            totals[staff_name] += minutes

        except Exception:
            issues.append(f"- {staff_name}: dữ liệu thời lượng lỗi")
    try:
        salary_sheet = spreadsheet.worksheet("02_Tinh_Luong")
    except Exception:
        salary_sheet = None
    total_payroll = 0
    if totals:
        for staff_name, minutes in totals.items():
            hours = minutes // 60
            mins = minutes % 60
            salary = round((minutes / 60) * rate)
            total_payroll += salary
            if salary_sheet:
                payroll_date = datetime.now(TZ).strftime("%d/%m/%Y")
                salary_records = salary_sheet.get_all_records()

                already_exists = False

                for row in salary_records:
                    row_text = str(row)

                    if (
                        payroll_date in row_text
                        and staff_name in row_text
                        and "Tạm tính tuần" in row_text
                    ):
                        already_exists = True
                        break

                if not already_exists:
                    salary_sheet.append_row(
                        [
                            payroll_date,
                            staff_name,
                            f"{hours} giờ {mins} phút",
                            salary,
                            "Tạm tính tuần"
                        ],
                        value_input_option="RAW",
                        insert_data_option="INSERT_ROWS"
)
                    sheet_status = "Đã ghi vào 02_Tinh_Luong"
                else:
                    sheet_status = "Đã có trong 02_Tinh_Luong, không ghi trùng"
            lines.append(f"👤 {staff_name}")
            lines.append(f"- Tổng giờ: {hours} giờ {mins} phút")
            lines.append(f"- Lương tạm: {salary:,}đ".replace(",", "."))
            lines.append(f"- Sheet: {sheet_status}")
            lines.append("")
    else:
        lines.append("Chưa có dữ liệu đủ CHECKIN/CHECKOUT để tính lương.")
        lines.append("")
    if totals:
        lines.append(f"💰 Tổng payroll tuần: {total_payroll:,}đ".replace(",", "."))
        lines.append("")
    if issues:
        lines.append("⚠️ Dữ liệu cần Mr.Win kiểm tra:")
        lines.extend(sorted(issues))

    await update.message.reply_text("\n".join(lines))
async def fixcheckin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("⛔ Chỉ admin mới được sửa chấm công.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ Cách dùng: /fixcheckin Tên HH:MM")
        return

    staff_name = " ".join(context.args[:-1]).strip().title()
    fix_time = context.args[-1].strip()
    today = datetime.now(TZ).strftime("%d/%m/%Y")

    sheet = get_worksheet("01_Cham_Cong")
    if not sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet 01_Cham_Cong.")
        return

    records = sheet.get_all_records()

    for idx in range(len(records) - 1, -1, -1):
        row = records[idx]
        row_index = idx + 2

        if (
            row.get("Ngày") == today
            and str(row.get("Nhân viên", "")).strip().lower() == staff_name.lower()
        ):
            sheet.update(
                f"C{row_index}",
                [[fix_time]],
                value_input_option="RAW"
            )
            sheet.format(f"C{row_index}", {
                "horizontalAlignment": "LEFT"
            })
            await update.message.reply_text(f"✅ Đã sửa CHECKIN {staff_name} thành {fix_time}")
            return

    await update.message.reply_text(f"⚠️ Không tìm thấy dòng chấm công hôm nay của {staff_name}.")


async def fixcheckout_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("⛔ Chỉ admin mới được sửa chấm công.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ Cách dùng: /fixcheckout Tên HH:MM")
        return

    staff_name = " ".join(context.args[:-1]).strip().title()
    fix_time = context.args[-1].strip()
    today = datetime.now(TZ).strftime("%d/%m/%Y")

    sheet = get_worksheet("01_Cham_Cong")
    if not sheet:
        await update.message.reply_text("❌ Không kết nối được Google Sheet 01_Cham_Cong.")
        return

    records = sheet.get_all_records()

    for idx in range(len(records) - 1, -1, -1):
        row = records[idx]
        row_index = idx + 2

        if (
            row.get("Ngày") == today
            and str(row.get("Nhân viên", "")).strip().lower() == staff_name.lower()
        ):
            sheet.update(
                f"D{row_index}",
                [[fix_time]],
                value_input_option="RAW"
            )
            
            await update.message.reply_text(f"✅ Đã sửa CHECKOUT {staff_name} thành {fix_time}")
            return

    await update.message.reply_text(f"⚠️ Không tìm thấy dòng chấm công hôm nay của {staff_name}.")
async def clearattendance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    DATA.setdefault("attendance", {})
    DATA["attendance"][chat_id] = {}
    save_data(DATA)

    await update.message.reply_text(
        "✅ Đã xóa sạch dữ liệu chấm công của nhóm này.\n\n"
        "Các lệnh CHECKIN / CHECKOUT vẫn dùng bình thường.\n"
        "Nhân viên có thể bắt đầu chấm công lại từ đầu."
    )
async def payrollmonth_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    rate = 30000
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)

    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("⛔ Chỉ admin mới được xem bảng lương tháng.")
        return

    now_dt = datetime.now(TZ)
    current_month = now_dt.strftime("%Y-%m")
    try:
        spreadsheet = gs_client.open_by_key("1-2CUwuORi7L4HlUMx7n7uUVhMIFXL0_95PVp3_LGGe8")
        sheet = spreadsheet.worksheet("01_Cham_Cong")
        records = sheet.get_all_records()
        salary_sheet = spreadsheet.worksheet("02_Tinh_Luong")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc Google Sheet:\n{e}")
        return
    totals = {}
    issues = []
    salary_data = DATA.get("salary", {}).get(chat_id, {})
    fixed_staff = []    
    for row in records:
        date_text = str(row.get("Ngày", "")).strip()
        staff_name = str(row.get("Nhân viên", "")).strip()
        duration_text = str(row.get("Thời lượng", "")).strip()

        if not date_text or not staff_name or not duration_text:
            continue

        if not date_text.endswith(now_dt.strftime("%Y")) or not date_text[3:5] == now_dt.strftime("%m"):
            continue
        try:
            hours = 0
            mins = 0

            if "giờ" in duration_text:
                parts = duration_text.split("giờ")
                hours = int(parts[0].strip())
                if len(parts) > 1 and "phút" in parts[1]:
                    mins = int(parts[1].replace("phút", "").strip())
            elif "phút" in duration_text:
                mins = int(duration_text.replace("phút", "").strip())

            minutes = hours * 60 + mins

            if minutes <= 0:
                continue

            totals.setdefault(staff_name, 0)
            totals[staff_name] += minutes

        except Exception:
            issues.append(f"- {staff_name}: dữ liệu thời lượng lỗi")
                
    for staff_name, info in salary_data.items():
        if info.get("type") == "fixed":
            fixed_salary = info.get("fixed_salary", 0)
            fixed_staff.append((staff_name, fixed_salary))
    lines = [f"✅ BẢNG LƯƠNG CHỐT THÁNG {now_dt.strftime('%m/%Y')}", ""]    
    if totals or fixed_staff:
        for staff_name, minutes in totals.items():
            hours = minutes // 60
            mins = minutes % 60
            salary = round((minutes / 60) * rate)
            salary_records = salary_sheet.get_all_records()
            already_exists = any(
                now_dt.strftime("%m/%Y") in str(row)
                and staff_name in str(row)
                and "Chốt lương tháng" in str(row)
                for row in salary_records
            )

            if not already_exists:
                salary_sheet.append_row([
                    now_dt.strftime("%d/%m/%Y"),
                    staff_name,
                    f"{hours} giờ {mins} phút",
                    salary,
                    "Chốt lương tháng"
                ])

            lines.append(f"👤 {staff_name}")
            lines.append(f"- Tổng giờ: {hours} giờ {mins} phút")
            lines.append(f"- Lương tạm: {salary:,}đ".replace(",", "."))
            lines.append("")
        for staff_name, fixed_salary in fixed_staff:
            lines.append(f"👤 {staff_name}")
            lines.append("- Loại lương: Lương cứng")
            lines.append(f"- Lương tháng: {fixed_salary:,}đ".replace(",", "."))
            lines.append("")
            
    else:
        lines.append("Chưa có dữ liệu đủ CHECKIN/CHECKOUT để tính lương tháng.")
        lines.append("")

    if issues:
        lines.append("⚠️ Dữ liệu cần Mr.Win kiểm tra:")
        lines.extend(issues)

    await update.message.reply_text("\n".join(lines))
async def payrollfinal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): 
    chat_id = str(update.effective_chat.id)
    now_dt = datetime.now(TZ)
    final_key = now_dt.strftime("%Y-%m")

    DATA.setdefault("payroll_final_lock", {}).setdefault(chat_id, {})

    if DATA["payroll_final_lock"][chat_id].get(final_key):
        await update.message.reply_text("⚠️ Bảng lương tháng này đã được chốt trước đó.")
        return

    DATA["payroll_final_lock"][chat_id][final_key] = True
    save_data(DATA)
    

    await payrollmonth_cmd(update, context)

    await update.message.reply_text(
        "✅ Đã chốt bảng lương tháng."
    )
async def payrolllock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    now_dt = datetime.now(TZ)
    lock_key = now_dt.strftime("%Y-%m")

    DATA.setdefault("payroll_lock", {})
    DATA["payroll_lock"].setdefault(chat_id, {})

    if DATA["payroll_lock"][chat_id].get(lock_key):
        await update.message.reply_text(
            f"⚠️ Payroll tháng {lock_key} đã được khóa trước đó."
        )
        return

    DATA["payroll_lock"][chat_id][lock_key] = True
    save_data(DATA)

    await update.message.reply_text(
        f"🔒 Đã khóa payroll tháng {lock_key}."
    )
async def payrollunlock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    now_dt = datetime.now(TZ)
    lock_key = now_dt.strftime("%Y-%m")

    DATA.setdefault("payroll_lock", {}).setdefault(chat_id, {})

    if DATA["payroll_lock"][chat_id].get(lock_key):
        del DATA["payroll_lock"][chat_id][lock_key]
        save_data(DATA)

        await update.message.reply_text(
            f"🔓 Đã mở khóa payroll tháng {lock_key}."
        )
    else:
        await update.message.reply_text(
            "⚠️ Tháng này chưa bị khóa."
        )
async def payslip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Cú pháp: /payslip Tên_nhân_viên")
        return

    staff_name = " ".join(context.args).strip()
    chat_id = str(update.effective_chat.id)
    now_dt = datetime.now(TZ)

    salary_data = DATA.get("salary", {}).get(chat_id, {})
    staff_salary = salary_data.get(staff_name, {})

    if staff_salary.get("type") == "fixed":
        fixed_salary = staff_salary.get("fixed_salary", 0)

        await update.message.reply_text(
            f"🧾 PHIẾU LƯƠNG {now_dt.strftime('%m/%Y')}\n\n"
            f"👤 Nhân viên: {staff_name}\n"
            f"- Loại lương: Lương cứng\n"
            f"- Lương tháng: {fixed_salary:,}đ".replace(",", ".")
        )
        return

    try:
        spreadsheet = gs_client.open_by_key("1-2CUwuORi7L4HlUMx7n7uUVhMIFXL0_95PVp3_LGGe8")
        sheet = spreadsheet.worksheet("01_Cham_Cong")
        records = sheet.get_all_records()
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc Google Sheet:\n{e}")
        return

    total_minutes = 0

    for row in records:
        date_text = str(row.get("Ngày", "")).strip()
        name_text = str(row.get("Nhân viên", "")).strip()
        duration_text = str(row.get("Thời lượng", "")).strip()
        checkin_text = str(row.get("Checkin", "")).strip()

        if name_text != staff_name:
            continue

        if not date_text.endswith(now_dt.strftime("%Y")) or date_text[3:5] != now_dt.strftime("%m"):
            continue

        try:
            hours = 0
            mins = 0

            if "giờ" in duration_text:
                parts = duration_text.split("giờ")
                hours = int(parts[0].strip())
                if len(parts) > 1 and "phút" in parts[1]:
                    mins = int(parts[1].replace("phút", "").strip())
            elif "phút" in duration_text:
                mins = int(duration_text.replace("phút", "").strip())

            worked_minutes = hours * 60 + mins

            date_obj = datetime.strptime(date_text, "%d/%m/%Y")
            weekday = date_obj.weekday()

            if weekday == 6:
                paid_minutes = 0
            elif weekday == 0:
                paid_minutes = min(worked_minutes, 360)
            else:
                checkin_hour = int(checkin_text.split(":")[0]) if ":" in checkin_text else 0

                if checkin_hour >= 17:
                    paid_minutes = min(worked_minutes, 240)
                else:
                    paid_minutes = min(worked_minutes, 300)

            total_minutes += paid_minutes
        except Exception as e:
            pass

    hours = total_minutes // 60
    mins = total_minutes % 60
    hourly_rate = DATA.get("salary", {}).get(chat_id, {}).get(staff_name, {}).get("hourly_rate", 30000)
    salary_type = DATA.get("salary", {}).get(chat_id, {}).get(staff_name, {}).get("type", "hourly")

    fixed_salary = DATA.get("salary", {}).get(chat_id, {}).get(staff_name, {}).get("fixed_salary", 0)

    if salary_type == "fixed":
        salary = fixed_salary
    else:
        salary = round((total_minutes / 60) * hourly_rate)
    bonus = DATA.get("bonus", {}).get(chat_id, {}).get(staff_name, 0)
    advance = DATA.get("advance", {}).get(chat_id, {}).get(staff_name, 0)
    fine = DATA.get("fine", {}).get(chat_id, {}).get(staff_name, 0)

    final_salary = salary + bonus - advance - fine
    if salary_type == "fixed":
        type_text = "Lương cứng"
        rate_text = f"{fixed_salary:,}đ/tháng"
    else:
        type_text = "Theo giờ"
        rate_text = f"{hourly_rate:,}đ/h"
    await update.message.reply_text(
        f"🧾 PHIẾU LƯƠNG {now_dt.strftime('%m/%Y')}\n\n"
        f"👤 Nhân viên: {staff_name}\n"
        f"– Loại lương: {type_text}\n"
        f"- Tổng giờ: {hours} giờ {mins} phút\n"
        f"– Đơn giá: {rate_text}\n"
        f"- Lương tạm: {salary:,}đ\n"
        f"- Thưởng: {bonus:,}đ\n"
        f"- Ứng lương: {advance:,}đ\n"
        f"- Phạt: {fine:,}đ\n"
        f"-------------------\n"
        f"💰 Thực nhận: {final_salary:,}đ"
        .replace(",", ".")
    )
async def salarytype_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if len(context.args) < 2:
        await update.message.reply_text(
            "Cách dùng:\n"
            "/salarytype Tên hourly\n"
            "/salarytype Tên fixed\n\n"
            "Ví dụ:\n"
            "/salarytype Huy hourly\n"
            "/salarytype Mr.Happy fixed"
        )
        return

    staff_name = context.args[0].strip()
    salary_type = context.args[1].strip().lower()

    if salary_type not in ["hourly", "fixed"]:
        await update.message.reply_text(
            "❌ Loại lương không hợp lệ.\n"
            "Chỉ dùng: hourly hoặc fixed"
        )
        return

    DATA.setdefault("salary", {}).setdefault(chat_id, {})
    DATA["salary"][chat_id].setdefault(staff_name, {})
    DATA["salary"][chat_id][staff_name]["type"] = salary_type
    save_data(DATA)

    type_text = "Theo giờ" if salary_type == "hourly" else "Lương cứng"

    await update.message.reply_text(
        f"✅ Đã cập nhật loại lương cho {staff_name}:\n"
        f"{type_text}"
    )
def sync_salary_to_sheet(staff_name, salary_type, hourly_rate="", fixed_salary=""):
    try:
        ws = get_worksheet("022_Cau_Hinh_Luong")
        if not ws:
            print("KHONG MO DUOC SHEET 022_Cau_Hinh_Luong")
            return

        rows = ws.get_all_values()
        found = False

        for idx, row in enumerate(rows[1:], start=2):
            name = row[0].strip() if len(row) > 0 else ""
            if name.lower() == staff_name.lower():
                ws.update_cell(idx, 2, salary_type)
                ws.update_cell(idx, 3, hourly_rate)
                ws.update_cell(idx, 4, fixed_salary)
                ws.update_cell(idx, 5, datetime.now(TZ).strftime("%d/%m/%Y"))
                found = True
                break

        if not found:
            ws.append_row([
                staff_name,
                salary_type,
                hourly_rate,
                fixed_salary,
                datetime.now(TZ).strftime("%d/%m/%Y"),
                "Cập nhật từ Telegram"
            ])

    except Exception as e:
        print("LOI DONG BO LUONG SHEET:", e)
def sync_reward_to_sheet(staff_name, action_type, amount, note=""):
    try:
        ws = get_worksheet("023_Thuong_Ung_Phat")

        if not ws:
            print("KHONG MO DUOC SHEET 023_Thuong_Ung_Phat")
            return

        ws.append_row([
            datetime.now(TZ).strftime("%d/%m/%Y"),
            staff_name,
            action_type,
            amount,
            note
        ])

    except Exception as e:
        print("LOI GHI THUONG_UNG_PHAT:", e)
def get_reward_data_from_sheet():
    reward_data = {}

    try:
        ws = get_worksheet("023_Thuong_Ung_Phat")
        if not ws:
            print("KHONG MO DUOC SHEET 023_Thuong_Ung_Phat")
            return reward_data

        records = ws.get_all_records()

        for row in records:
            staff_name = str(row.get("Nhân viên", "")).strip()
            action_type = str(row.get("Loại", "")).strip().lower()
            amount = row.get("Số tiền", 0)

            if not staff_name or not action_type:
                continue

            try:
                amount = int(str(amount).replace(".", "").replace(",", "").strip() or 0)
            except:
                amount = 0

            reward_data.setdefault(staff_name, {
                "bonus": 0,
                "advance": 0,
                "fine": 0
            })

            if action_type in ["bonus", "thuong", "thưởng"]:
                reward_data[staff_name]["bonus"] += amount
            elif action_type in ["advance", "ung", "ứng"]:
                reward_data[staff_name]["advance"] += amount
            elif action_type in ["fine", "phat", "phạt"]:
                reward_data[staff_name]["fine"] += amount

    except Exception as e:
        print("LOI DOC THUONG_UNG_PHAT SHEET:", e)

    return reward_data
def get_salary_config_from_sheet():
    salary_config = {}

    try:
        ws = get_worksheet("022_Cau_Hinh_Luong")
        if not ws:
            print("KHONG MO DUOC SHEET 022_Cau_Hinh_Luong")
            return salary_config

        records = ws.get_all_records()

        for row in records:
            staff_name = str(row.get("Tên nhân viên", "")).strip()
            if not staff_name:
                continue

            salary_type = str(row.get("Loại lương", "hourly")).strip().lower()
            hourly_rate = row.get("Lương giờ", 30000)
            fixed_salary = row.get("Lương cứng", 0)

            try:
                hourly_rate = int(str(hourly_rate).replace(".", "").replace(",", "").strip() or 30000)
            except:
                hourly_rate = 30000

            try:
                fixed_salary = int(str(fixed_salary).replace(".", "").replace(",", "").strip() or 0)
            except:
                fixed_salary = 0

            salary_config[staff_name] = {
                "type": salary_type,
                "hourly_rate": hourly_rate,
                "fixed_salary": fixed_salary,
            }

    except Exception as e:
        print("LOI DOC CAU HINH LUONG SHEET:", e)

    return salary_config
async def sethourly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if len(context.args) < 2:
        await update.message.reply_text(
            "Cách dùng:\n"
            "/sethourly Tên số_tiền\n\n"
            "Ví dụ:\n"
            "/sethourly Huy 30000\n"
            "/sethourly Thao 25000"
        )
        return

    staff_name = context.args[0].strip()

    amount_text = (
        context.args[1]
        .replace(".", "")
        .replace(",", "")
        .replace("đ", "")
        .strip()
    )

    try:
        hourly_rate = int(amount_text)
    except:
        await update.message.reply_text("❌ Số tiền không hợp lệ.")
        return

    DATA.setdefault("salary", {}).setdefault(chat_id, {})
    DATA["salary"][chat_id].setdefault(staff_name, {})

    DATA["salary"][chat_id][staff_name]["hourly_rate"] = hourly_rate

    save_data(DATA)
    sync_salary_to_sheet(staff_name, "hourly", hourly_rate, "")

    await update.message.reply_text(
        f"✅ Đã cập nhật lương giờ cho {staff_name}:\n"
        f"{hourly_rate:,}đ/giờ".replace(",", ".")
    )
async def fixedsalary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if len(context.args) < 2:
        await update.message.reply_text(
            "Cách dùng:\n"
            "/fixedsalary Tên số_tiền\n\n"
            "Ví dụ:\n"
            "/fixedsalary Mr.Happy 8000000"
        )
        return

    staff_name = context.args[0].strip()
    amount_text = context.args[1].replace(".", "").replace(",", "").replace("đ", "").strip()

    try:
        amount = int(amount_text)
    except Exception:
        await update.message.reply_text("❌ Số tiền không hợp lệ.")
        return

    DATA.setdefault("salary", {}).setdefault(chat_id, {})
    DATA["salary"][chat_id].setdefault(staff_name, {})
    DATA["salary"][chat_id][staff_name]["type"] = "fixed"
    DATA["salary"][chat_id][staff_name]["fixed_salary"] = amount
    print(DATA["salary"])
    save_data(DATA)
    sync_salary_to_sheet(staff_name, "fixed", "", amount)

    await update.message.reply_text(
        f"✅ Đã cập nhật lương cứng cho {staff_name}:\n"
        f"{amount:,}đ/tháng".replace(",", ".")
    )

async def bonus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Cú pháp: /bonus Tên_nhân_viên số_tiền"
        )
        return

    staff_name = context.args[0].strip().title()
    
    try:
        amount = int(context.args[1])
    except:
        await update.message.reply_text("❌ Số tiền không hợp lệ.")
        return

    chat_id = str(update.effective_chat.id)

    
    sync_reward_to_sheet(
        staff_name,
        "bonus",
        amount
    )
    

    await update.message.reply_text(
        f"🎉 Đã cộng thưởng cho {staff_name}: "
        f"{amount:,}đ".replace(",", ".")
    )
async def bonusremove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Cú pháp: /bonusremove Tên_nhân_viên số_tiền")
        return

    staff_name = context.args[0].strip().title()

    try:
        amount = int(context.args[1])
    except:
        await update.message.reply_text("❌ Số tiền không hợp lệ.")
        return



    current_bonus = DATA.get("bonus", {}).get(chat_id, {}).get(staff_name, 0)
    new_bonus = max(0, current_bonus - amount)

    DATA.setdefault("bonus", {}).setdefault(chat_id, {})
    DATA["bonus"][chat_id][staff_name] = new_bonus

    save_data(DATA)

    await update.message.reply_text(
        f"➖ Đã huỷ thưởng của {staff_name}: {amount:,}đ\n"
        f"🎉 Thưởng còn lại: {new_bonus:,}đ".replace(",", ".")
    )   
async def advance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Cú pháp: /advance Tên_nhân_viên số_tiền")
        return

    staff_name = context.args[0].strip().title()

    try:
        amount = int(context.args[1])
    except:
        await update.message.reply_text("❌ Số tiền không hợp lệ.")
        return

    
    sync_reward_to_sheet(
        staff_name,
        "advance",
        amount
    )

    await update.message.reply_text(
        f"💸 Đã ghi ứng lương cho {staff_name}: "
        f"{amount:,}đ".replace(",", ".")
    )
async def fine_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Cú pháp: /fine Tên_nhân_viên số_tiền"
        )
        return

    staff_name = context.args[0].strip().title()

    try:
        amount = int(context.args[1])
    except:
        await update.message.reply_text("❌ Số tiền không hợp lệ.")
        return


    
    sync_reward_to_sheet(
        staff_name,
        "fine",
        amount
    )
    
    await update.message.reply_text(
        f"⚠️ Đã ghi phạt cho {staff_name}: "
        f"{amount:,}đ".replace(",", ".")
    ) 
async def fineremove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Cú pháp: /fineremove Tên_nhân_viên số_tiền")
        return

    staff_name = context.args[0].strip().title()

    try:
        amount = int(context.args[1])
    except:
        await update.message.reply_text("❌ Số tiền không hợp lệ.")
        return

    chat_id = str(update.effective_chat.id)

    current_fine = DATA.get("fine", {}).get(chat_id, {}).get(staff_name, 0)
    new_fine = max(0, current_fine - amount)

    DATA.setdefault("fine", {}).setdefault(chat_id, {})
    DATA["fine"][chat_id][staff_name] = new_fine

    save_data(DATA)

    await update.message.reply_text(
        f"➖ Đã huỷ phạt của {staff_name}: {amount:,}đ\n"
        f"⚠️ Phạt còn lại: {new_fine:,}đ".replace(",", ".")
    ) 
async def resetpayroll_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    DATA.setdefault("bonus", {}).pop(chat_id, None)
    DATA.setdefault("advance", {}).pop(chat_id, None)
    DATA.setdefault("fine", {}).pop(chat_id, None)

    save_data(DATA)

    await update.message.reply_text(
        "🧹 Đã reset thưởng / ứng / phạt của nhóm này."
    ) 
async def finelist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    fine_data = DATA.get("fine", {}).get(chat_id, {})

    if not fine_data:
        await update.message.reply_text("📭 Hiện chưa có dữ liệu phạt.")
        return

    lines = ["⚠️ DANH SÁCH PHẠT NHÂN VIÊN\n"]

    total_fine = 0

    for staff_name, amount in fine_data.items():
        lines.append(f"👤 {staff_name}: {amount:,}đ".replace(",", "."))
        total_fine += amount

    lines.append("")
    lines.append(f"💸 Tổng phạt: {total_fine:,}đ".replace(",", "."))

    await update.message.reply_text("\n".join(lines))       
async def salarylist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    salary_data = get_salary_config_from_sheet()

    if not salary_data:
        await update.message.reply_text("Chưa có cấu hình lương.")
        return

    lines = ["💼 CẤU HÌNH LƯƠNG TF", ""]

    for staff_name, info in salary_data.items():
        salary_type = info.get("type", "hourly")

        lines.append(f"👤 {staff_name}")

        if salary_type == "fixed":
            fixed_salary = info.get("fixed_salary", 0)
            lines.append("- Loại lương: Lương cứng")
            lines.append(f"- Mức: {fixed_salary:,}đ/tháng".replace(",", "."))
        else:
            hourly_rate = info.get("hourly_rate", 30000)
            lines.append("- Loại lương: Theo giờ")
            lines.append(f"- Mức: {hourly_rate:,}đ/giờ".replace(",", "."))
        lines.append("")

    await update.message.reply_text("\n".join(lines))
async def payrollsummary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    now_dt = datetime.now(TZ)

    salary_data = get_salary_config_from_sheet()
    reward_data = get_reward_data_from_sheet()

    all_staff = set()
    try:
        spreadsheet = gs_client.open_by_key("1-2CUwuORi7L4HlUMx7n7uUVhMIFXL0_95PVp3_LGGe8")
        sheet = spreadsheet.worksheet("01_Cham_Cong")
        records = sheet.get_all_records()

        for row in records:
            staff = str(row.get("Nhân viên", "")).strip()
            if staff:
                all_staff.add(staff)
    except Exception:
        pass

    for row in salary_data:
        all_staff.add(row)
    for row in reward_data:
        all_staff.add(row)

    lines = [f"📊 TỔNG KẾT LƯƠNG TF {now_dt.strftime('%m/%Y')}", ""]
    total_all = 0

    for staff_name in all_staff:
        info = salary_data.get(staff_name, {})
        salary_type = info.get("type", "hourly")

        bonus = reward_data.get(staff_name, {}).get("bonus", 0)
        advance = reward_data.get(staff_name, {}).get("advance", 0)
        fine = reward_data.get(staff_name, {}).get("fine", 0)

        if salary_type == "fixed":
            salary = info.get("fixed_salary", 0)
        else:
            total_minutes = 0

            try:
                spreadsheet = gs_client.open_by_key("1-2CUwuORi7L4HlUMx7n7uUVhMIFXL0_95PVp3_LGGe8")
                sheet = spreadsheet.worksheet("01_Cham_Cong")
                records = sheet.get_all_records()

                for row in records:
                    date_text = str(row.get("Ngày", "")).strip()
                    name_text = str(row.get("Nhân viên", "")).strip()
                    duration_text = str(row.get("Thời lượng", "")).strip()

                    if name_text != staff_name:
                        continue

                    if not date_text.endswith(now_dt.strftime("%Y")) or date_text[3:5] != now_dt.strftime("%m"):
                        continue

                    hours = 0
                    mins = 0

                    if "giờ" in duration_text:
                        parts = duration_text.split("giờ")
                        hours = int(parts[0].strip())
                        if len(parts) > 1 and "phút" in parts[1]:
                            mins = int(parts[1].replace("phút", "").strip())
                    elif "phút" in duration_text:
                        mins = int(duration_text.replace("phút", "").strip())

                    total_minutes += hours * 60 + mins

            except Exception:
                pass
            hourly_rate = info.get("hourly_rate", 30000)
            salary = round((total_minutes / 60) * hourly_rate)
            

        final_salary = salary + bonus - advance - fine

        if final_salary == 0:
            continue
        
        total_all += final_salary

        lines.extend([
            f"👤 {staff_name}",
            f"- Lương: {salary:,}đ".replace(",", "."),
            f"- Thưởng: {bonus:,}đ".replace(",", "."),
            f"- Ứng: {advance:,}đ".replace(",", "."),
            f"- Phạt: {fine:,}đ".replace(",", "."),
            f"💰 Thực nhận: {final_salary:,}đ".replace(",", "."),
            ""
        ])

    lines.append("-------------------")
    lines.append(f"🏦 Tổng thực chi: {total_all:,}đ".replace(",", "."))

    await update.message.reply_text("\n".join(lines))
def payroll_export_exists(month_text):
    try:
        ws = get_worksheet("02_Tinh_Luong")
        if not ws:
            return False

        records = ws.get_all_records()

        for row in records:
            date_text = str(row.get("Ngày", "")).strip()
            note_text = str(row.get("Ghi chú", "")).strip()

            if len(date_text) >= 10:
                if date_text[3:10] == month_text and note_text == "Chốt lương tháng":
                    return True

        return False

    except Exception as e:
        print("LOI KIEM TRA TRUNG XUAT LUONG:", e)
        return False
def export_payroll_to_sheet(rows):
    try:
        ws = get_worksheet("02_Tinh_Luong")
        if not ws:
            print("KHONG MO DUOC SHEET 02_Tinh_Luong")
            return False

        ws.append_rows(rows)

        return True

    except Exception as e:
        print("LOI GHI 02_Tinh_Luong:", e)
        return False
async def payrollexport_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now_dt = datetime.now(TZ)
    month_text = now_dt.strftime("%m/%Y")

    if payroll_export_exists(month_text):
        await update.message.reply_text(
            f"⚠️ Lương tháng {month_text} đã được xuất trước đó.\n"
            "Không thể xuất lại để tránh trùng dữ liệu."
        )
        return

    salary_data = get_salary_config_from_sheet()
    reward_data = get_reward_data_from_sheet()

    export_rows = []

    all_staff = set()

    try:
        ws = get_worksheet("01_Cham_Cong")
        records = ws.get_all_records()

        for row in records:
            staff = str(row.get("Nhân viên", "")).strip()
            if staff:
                all_staff.add(staff)
    except Exception:
        pass

    for row in salary_data:
        all_staff.add(row)

    for row in reward_data:
        all_staff.add(row)

    for staff_name in all_staff:
        info = salary_data.get(staff_name, {})
        salary_type = info.get("type", "hourly")

        reward = reward_data.get(staff_name, {})
        bonus = reward.get("bonus", 0)
        advance = reward.get("advance", 0)
        fine = reward.get("fine", 0)

        total_minutes = 0

        if salary_type == "fixed":
            salary = info.get("fixed_salary", 0)
            total_time_text = "Lương cứng"
        else:
            try:
                ws = get_worksheet("01_Cham_Cong")
                records = ws.get_all_records()

                for row in records:
                    date_text = str(row.get("Ngày", "")).strip()
                    name_text = str(row.get("Nhân viên", "")).strip()
                    duration_text = str(row.get("Thời lượng", "")).strip()

                    if name_text != staff_name:
                        continue

                    if not date_text.endswith(now_dt.strftime("%Y")) or date_text[3:5] != now_dt.strftime("%m"):
                        continue

                    hours = 0
                    mins = 0

                    if "giờ" in duration_text:
                        parts = duration_text.split("giờ")
                        hours = int(parts[0].strip())
                        if len(parts) > 1 and "phút" in parts[1]:
                            mins = int(parts[1].replace("phút", "").strip())
                    elif "phút" in duration_text:
                        mins = int(duration_text.replace("phút", "").strip())

                    total_minutes += hours * 60 + mins

            except Exception:
                pass

            hourly_rate = info.get("hourly_rate", 30000)
            salary = round((total_minutes / 60) * hourly_rate)

            hours = total_minutes // 60
            mins = total_minutes % 60
            total_time_text = f"{hours} giờ {mins} phút"

        final_salary = salary + bonus - advance - fine

        if final_salary == 0:
            continue

        export_rows.append([
            now_dt.strftime("%d/%m/%Y"),
            staff_name,
            total_time_text,
            salary,
            bonus,
            advance,
            fine,
            final_salary,
            "Chốt lương tháng"
        ])

    if not export_rows:
        await update.message.reply_text("❌ Không có dữ liệu lương để xuất.")
        return

    ok = export_payroll_to_sheet(export_rows)

    if not ok:
        await update.message.reply_text("❌ Lỗi ghi vào sheet 02_Tinh_Luong.")
        return

    await update.message.reply_text(
        f"✅ Đã xuất bảng lương tháng {now_dt.strftime('%m/%Y')} vào sheet 02_Tinh_Luong.\n"
        f"Số dòng: {len(export_rows)}"
    )


def schedule_monthly_item(app, chat_id: str, index: int, item: dict):
    hour, minute = map(int, item["time"].split(":"))
    remind_time = datetime.now(TZ).replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0
    ).timetz()

    app.job_queue.run_daily(

        monthly_reminder_job,
        time=remind_time,
        data={
            "chat_id": chat_id,
            "day": item["day"],
            "time": item["time"],
            "text": item["text"],
        },
        name=f"monthly_{chat_id}_{index}"
    )


def schedule_monthly_all(app):
    monthly_data = DATA.get("monthly", {})

    for chat_id, items in monthly_data.items():
        for index, item in enumerate(items):
            schedule_monthly_item(app, chat_id, index, item)


async def addmonthly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if len(context.args) < 3:
        await update.message.reply_text(
            "Cách dùng:\n"
            "/addmonthly ngày giờ nội_dung\n\n"
            "Ví dụ:\n"
            "/addmonthly 5 08:00 Đóng tiền Bảo Hiểm Xã Hội"
        )
        return

    try:
        day = int(context.args[0])
        time_text = context.args[1].strip()
        datetime.strptime(time_text, "%H:%M")
    except Exception:
        await update.message.reply_text(
            "❌ Sai định dạng.\n"
            "Ví dụ đúng:\n"
            "/addmonthly 5 08:00 Đóng tiền Bảo Hiểm Xã Hội"
        )
        return

    if day < 1 or day > 31:
        await update.message.reply_text("❌ Ngày phải từ 1 đến 31.")
        return

    text = " ".join(context.args[2:]).strip()

    if not text:
        await update.message.reply_text("❌ Nội dung nhắc không được để trống.")
        return

    DATA.setdefault("monthly", {}).setdefault(chat_id, [])

    item = {
        "day": day,
        "time": time_text,
        "text": text,
    }

    DATA["monthly"][chat_id].append(item)
    save_data(DATA)

    index = len(DATA["monthly"][chat_id]) - 1
    schedule_monthly_item(context.application, chat_id, index, item)

    await update.message.reply_text(
        "✅ Đã thêm lịch nhắc hằng tháng:\n"
        f"- Ngày: {day} Tây hằng tháng\n"
        f"- Giờ: {time_text}\n"
        f"- Nội dung: {text}"
    )


async def monthlylist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    items = DATA.get("monthly", {}).get(chat_id, [])

    if not items:
        await update.message.reply_text("Chưa có lịch nhắc hằng tháng.")
        return

    lines = ["📅 LỊCH NHẮC HẰNG THÁNG", ""]

    for index, item in enumerate(items, start=1):
        lines.append(
            f"{index}. Ngày {item['day']} - {item['time']}\n"
            f"   {item['text']}"
        )

    await update.message.reply_text("\n".join(lines))


async def removemonthly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text(
            "Cách dùng:\n"
            "/removemonthly số_thứ_tự\n\n"
            "Ví dụ:\n"
            "/removemonthly 1"
        )
        return

    try:
        index = int(context.args[0]) - 1
    except Exception:
        await update.message.reply_text("❌ Số thứ tự không hợp lệ.")
        return

    items = DATA.get("monthly", {}).get(chat_id, [])

    if index < 0 or index >= len(items):
        await update.message.reply_text("❌ Không tìm thấy lịch nhắc này.")
        return

    removed = items.pop(index)
    save_data(DATA)

    await update.message.reply_text(
        "✅ Đã xóa lịch nhắc hằng tháng:\n"
        f"- Ngày {removed['day']} - {removed['time']}\n"
        f"- {removed['text']}"
    )
async def lunar_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    today_dt = datetime.now(TZ)
    today_date = today_dt.date()

    lunar_today = LunarDate.fromSolarDate(
        today_dt.year,
        today_dt.month,
        today_dt.day
    )

    try:
        target_solar = LunarDate(
            lunar_today.year,
            data["month"],
            data["day"]
        ).toSolarDate()
    except Exception:
        return

    remind_before_date = target_solar - timedelta(days=7)

    if today_date == remind_before_date:
        await context.bot.send_message(
            chat_id=data["chat_id"],
            text=(
                "🔔 NHẮC TRƯỚC GIỖ ÂM LỊCH\n\n"
                f"Còn 7 ngày nữa là ngày {data['day']:02d}/{data['month']:02d} âm lịch.\n"
                f"{data['text']}\n\n"
                "Sếp nhớ chuẩn bị đồ cúng, sắp xếp thời gian và nhắc người nhà."
            )
        )
        return

    if today_date == target_solar:
        await context.bot.send_message(
            chat_id=data["chat_id"],
            text=(
                "🕯 HÔM NAY LÀ GIỖ ÂM LỊCH\n\n"
                f"Hôm nay là ngày {data['day']:02d}/{data['month']:02d} âm lịch.\n"
                f"{data['text']}"
            )
        )
        return


def schedule_lunar_item(app, chat_id: str, index: int, item: dict):
    hour, minute = map(int, item["time"].split(":"))
    remind_time = datetime.now(TZ).replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0
    ).timetz()

    app.job_queue.run_daily(
        lunar_reminder_job,
        time=remind_time,
        data={
            "chat_id": chat_id,
            "day": item["day"],
            "month": item["month"],
            "time": item["time"],
            "text": item["text"],
        },
        name=f"lunar_{chat_id}_{index}"
    )


def schedule_lunar_all(app):
    lunar_data = DATA.get("lunar", {})

    for chat_id, items in lunar_data.items():
        for index, item in enumerate(items):
            schedule_lunar_item(app, chat_id, index, item)


async def addlunar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if len(context.args) < 4:
        await update.message.reply_text(
            "Cách dùng:\n"
            "/addlunar ngày_âm tháng_âm giờ nội_dung\n\n"
            "Ví dụ:\n"
            "/addlunar 01 08 08:00 Giỗ Ông cố"
        )
        return

    try:
        day = int(context.args[0])
        month = int(context.args[1])
        time_text = context.args[2].strip()
        datetime.strptime(time_text, "%H:%M")
    except Exception:
        await update.message.reply_text(
            "❌ Sai định dạng.\n"
            "Ví dụ đúng:\n"
            "/addlunar 01 08 08:00 Giỗ Ông cố"
        )
        return

    if day < 1 or day > 30:
        await update.message.reply_text("❌ Ngày âm phải từ 1 đến 30.")
        return

    if month < 1 or month > 12:
        await update.message.reply_text("❌ Tháng âm phải từ 1 đến 12.")
        return

    text = " ".join(context.args[3:]).strip()

    if not text:
        await update.message.reply_text("❌ Nội dung nhắc không được để trống.")
        return

    DATA.setdefault("lunar", {}).setdefault(chat_id, [])

    item = {
        "day": day,
        "month": month,
        "time": time_text,
        "text": text,
    }

    DATA["lunar"][chat_id].append(item)
    save_data(DATA)

    index = len(DATA["lunar"][chat_id]) - 1
    schedule_lunar_item(context.application, chat_id, index, item)

    await update.message.reply_text(
        "✅ Đã thêm lịch nhắc giỗ âm lịch hằng năm:\n"
        f"- Ngày âm: {day:02d}/{month:02d}\n"
        f"- Giờ: {time_text}\n"
        f"- Nội dung: {text}"
    )


async def lunarlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    items = DATA.get("lunar", {}).get(chat_id, [])

    if not items:
        await update.message.reply_text("Chưa có lịch nhắc giỗ âm lịch.")
        return

    lines = ["🕯 LỊCH GIỖ ÂM LỊCH HẰNG NĂM", ""]

    for index, item in enumerate(items, start=1):
        lines.append(
            f"{index}. Ngày âm {item['day']:02d}/{item['month']:02d} - {item['time']}\n"
            f"   {item['text']}"
        )

    await update.message.reply_text("\n".join(lines))


async def removelunar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text(
            "Cách dùng:\n"
            "/removelunar số_thứ_tự\n\n"
            "Ví dụ:\n"
            "/removelunar 1"
        )
        return

    try:
        index = int(context.args[0]) - 1
    except Exception:
        await update.message.reply_text("❌ Số thứ tự không hợp lệ.")
        return

    items = DATA.get("lunar", {}).get(chat_id, [])

    if index < 0 or index >= len(items):
        await update.message.reply_text("❌ Không tìm thấy lịch giỗ này.")
        return

    removed = items.pop(index)
    save_data(DATA)

    await update.message.reply_text(
        "✅ Đã xóa lịch giỗ âm lịch:\n"
        f"- Ngày âm {removed['day']:02d}/{removed['month']:02d} - {removed['time']}\n"
        f"- {removed['text']}"
    )
async def birthday_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    today_dt = datetime.now(TZ)
    today_date = today_dt.date()

    target_date = datetime(
        today_dt.year,
        data["month"],
        data["day"],
        tzinfo=TZ
    ).date()

    remind_before_date = target_date - timedelta(days=7)

    if today_date == remind_before_date:
        await context.bot.send_message(
            chat_id=data["chat_id"],
            text=(
                "🎂 NHẮC TRƯỚC SINH NHẬT\n\n"
                f"Còn 7 ngày nữa là {data['text']}.\n"
                "Sếp nhớ chuẩn bị quà, bánh hoặc sắp xếp kế hoạch."
            )
        )
        return

    if today_date == target_date:
        await context.bot.send_message(
            chat_id=data["chat_id"],
            text=(
                "🎉 HÔM NAY LÀ SINH NHẬT\n\n"
                f"{data['text']}"
            )
        )
        return


def schedule_birthday_item(app, chat_id: str, index: int, item: dict):
    hour, minute = map(int, item["time"].split(":"))
    remind_time = datetime.now(TZ).replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0
    ).timetz()

    app.job_queue.run_daily(
        birthday_reminder_job,
        time=remind_time,
        data={
            "chat_id": chat_id,
            "day": item["day"],
            "month": item["month"],
            "time": item["time"],
            "text": item["text"],
        },
        name=f"birthday_{chat_id}_{index}"
    )


def schedule_birthday_all(app):
    birthday_data = DATA.get("birthday", {})

    for chat_id, items in birthday_data.items():
        for index, item in enumerate(items):
            schedule_birthday_item(app, chat_id, index, item)


async def addbirthday_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if len(context.args) < 4:
        await update.message.reply_text(
            "Cách dùng:\n"
            "/addbirthday ngày tháng giờ nội_dung\n\n"
            "Ví dụ:\n"
            "/addbirthday 29 08 08:00 Sinh nhật bé Thiên Thư"
        )
        return

    try:
        day = int(context.args[0])
        month = int(context.args[1])
        time_text = context.args[2].strip()
        datetime.strptime(time_text, "%H:%M")
        datetime(datetime.now(TZ).year, month, day)
    except Exception:
        await update.message.reply_text(
            "❌ Sai định dạng hoặc ngày không hợp lệ.\n"
            "Ví dụ đúng:\n"
            "/addbirthday 29 08 08:00 Sinh nhật bé Thiên Thư"
        )
        return

    text = " ".join(context.args[3:]).strip()

    if not text:
        await update.message.reply_text("❌ Nội dung sinh nhật không được để trống.")
        return

    DATA.setdefault("birthday", {}).setdefault(chat_id, [])

    item = {
        "day": day,
        "month": month,
        "time": time_text,
        "text": text,
    }

    DATA["birthday"][chat_id].append(item)
    save_data(DATA)

    index = len(DATA["birthday"][chat_id]) - 1
    schedule_birthday_item(context.application, chat_id, index, item)

    await update.message.reply_text(
        "✅ Đã thêm lịch nhắc sinh nhật hằng năm:\n"
        f"- Ngày: {day:02d}/{month:02d}\n"
        f"- Giờ: {time_text}\n"
        f"- Nội dung: {text}"
    )


async def birthdaylist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    items = DATA.get("birthday", {}).get(chat_id, [])

    if not items:
        await update.message.reply_text("Chưa có lịch nhắc sinh nhật.")
        return

    lines = ["🎂 LỊCH SINH NHẬT HẰNG NĂM", ""]

    for index, item in enumerate(items, start=1):
        lines.append(
            f"{index}. Ngày {item['day']:02d}/{item['month']:02d} - {item['time']}\n"
            f"   {item['text']}"
        )

    await update.message.reply_text("\n".join(lines))


async def removebirthday_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text(
            "Cách dùng:\n"
            "/removebirthday số_thứ_tự\n\n"
            "Ví dụ:\n"
            "/removebirthday 1"
        )
        return

    try:
        index = int(context.args[0]) - 1
    except Exception:
        await update.message.reply_text("❌ Số thứ tự không hợp lệ.")
        return

    items = DATA.get("birthday", {}).get(chat_id, [])

    if index < 0 or index >= len(items):
        await update.message.reply_text("❌ Không tìm thấy lịch sinh nhật này.")
        return

    removed = items.pop(index)
    save_data(DATA)

    await update.message.reply_text(
        "✅ Đã xóa lịch sinh nhật:\n"
        f"- Ngày {removed['day']:02d}/{removed['month']:02d} - {removed['time']}\n"
        f"- {removed['text']}"
    )
async def tonkho_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ws = get_worksheet("07_Quan_Ly_Kho")
        if not ws:
            await update.message.reply_text("❌ Không kết nối được sheet 07_Quan_Ly_Kho.")
            return

        records = ws.get_all_records()
        records = [
            {
                str(k).replace("\n", "").strip(): v
                for k, v in row.items()
            }
            for row in records
        ]
        print(records)

        if not records:
            await update.message.reply_text("📦 Kho hiện chưa có dữ liệu.")
            return

        lines = ["📦 TỒN KHO TF\n"]

        for row in records:
            ten_hang = row.get("Tên hàng", "")
            ton_kho = row.get("Tồn kho", "")
            don_vi = row.get("Đơn vị", "")
            ton_toi_thieu = row.get("Tồn tối thiểu", "")
            trang_thai = row.get("Trạng thái", "")
            ten_hang = str(ten_hang).strip()
            if not ten_hang:
                continue
            icon = "🔴" if str(trang_thai).strip() == "Sắp hết" else "🟢"
            lines.append(
                f"{icon} {ten_hang}\n"
                f"📦 Tồn kho: {ton_kho} {don_vi}\n"
                f"📉 Tối thiểu: {ton_toi_thieu}\n"
                f"📋 Trạng thái: {trang_thai}"
            )
        await update.message.reply_text("\n\n".join(lines))

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi đọc tồn kho: {e}")

async def khohelp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📦 HƯỚNG DẪN NHÓM TF KHO & NHẬP HÀNG\n\n"
        "Nhóm này dùng để báo thiếu hàng, nhập hàng, kiểm kho và theo dõi hàng sắp hết.\n\n"
        "👤 PHÂN QUYỀN\n"
        "- Miss Uyên: người duyệt và chịu trách nhiệm cuối cùng.\n"
        "- Mr.Happy: theo dõi hàng thực tế, hỗ trợ báo thiếu hàng, nhập hàng, kiểm kho.\n"
        "- Mr.Win: hỗ trợ đối chiếu kho, chi phí và báo cáo.\n"
        "- Nhân viên: thấy thiếu hàng / hư hao phải báo ngay, không tự ý nhập nếu chưa duyệt.\n\n"
        "📌 CÁC LỆNH ĐANG DÙNG\n"
        "/tonkho - Xem tổng quan kho\n"
        "/nhaphang - Gửi mẫu nhập hàng\n"
        "/xuatkho - Gửi mẫu xuất kho\n"
        "/thieuhang - Gửi mẫu báo thiếu hàng\n"
        "/kiemkho - Gửi mẫu kiểm kho\n"
        "/khohelp - Xem hướng dẫn sử dụng nhóm kho\n\n"
        "⚠️ NGUYÊN TẮC BẮT BUỘC\n"
        "1. Gửi đúng mẫu, đúng tiêu đề.\n"
        "2. Báo thiếu hàng phải có mặt hàng, số lượng còn, mức độ.\n"
        "3. Nhập hàng phải có số lượng, đơn giá, tổng tiền, nhà cung cấp, người duyệt.\n"
        "4. Kiểm kho phải ghi rõ món còn đủ, món sắp hết, món cần nhập, hư hao nếu có.\n"
        "5. Phát sinh quan trọng phải báo ngay trong ngày.\n"
        "6. Tin nhắn sai mẫu có thể bot không ghi nhận.\n\n"
        "✅ Gửi đúng mẫu để TF quản lý kho rõ ràng, nhập hàng chuẩn xác và vận hành minh bạch."
    )
async def nhaphang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📥 MẪU NHẬP HÀNG TF\n\n"
        "NHẬP HÀNG - Tên người nhập\n\n"
        "Mặt hàng:\n"
        "Số lượng:\n"
        "Đơn giá:\n"
        "Tổng tiền:\n"
        "Nhà cung cấp:\n"
        "Hạn sử dụng:\n"
        "Người duyệt:\n"
        "Ghi chú:"
    )


async def thieuhang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚠️ MẪU BÁO THIẾU HÀNG TF\n\n"
        "THIẾU HÀNG - Tên người báo\n\n"
        "Mặt hàng:\n"
        "Số lượng còn:\n"
        "Mức độ: Gấp / Bình thường\n"
        "Dự kiến đủ dùng đến:\n"
        "Đề xuất nhập thêm:\n"
        "Ghi chú:"
    )

async def xuatkho_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📤 MẪU XUẤT KHO TF\n\n"
        "XUẤT KHO - Tên người xuất\n"
        "Mặt hàng:\n"
        "Số lượng xuất:\n"
        "Lý do:\n"
        "Ca:\n"
        "Ghi chú:"
    )
async def kiemkho_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 MẪU KIỂM KHO TF\n\n"
        "KIỂM KHO - Ngày\n\n"
        "Người kiểm:\n"
        "Các món còn đủ:\n"
        "Các món sắp hết:\n"
        "Các món cần nhập:\n"
        "Hàng gần hết hạn:\n"
        "Hàng hư hao / thất thoát nếu có:\n"
        "Ghi chú:"
    )
async def baocaokho_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📊 MẪU BÁO CÁO KHO CUỐI NGÀY TF\n\n"
        "BÁO CÁO KHO - Ngày\n\n"
        "Người báo cáo:\n"
        "Tình trạng kho hôm nay:\n"
        "Hàng đã nhập:\n"
        "Hàng còn thiếu:\n"
        "Hàng sắp hết:\n"
        "Hàng gần hết hạn:\n"
        "Hàng hư hao / thất thoát:\n"
        "Đề xuất xử lý:\n"
        "Người duyệt: Miss Uyên\n"
        "Ghi chú:"
    )
async def baocaokhotuan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📊 MẪU BÁO CÁO KHO CUỐI TUẦN TF\n\n"
        "BÁO CÁO KHO TUẦN - Tuần/Tháng\n\n"
        "Người báo cáo:\n"
        "Thời gian báo cáo:\n"
        "Tổng quan tình trạng kho:\n"
        "Hàng đã nhập trong tuần:\n"
        "Hàng còn thiếu:\n"
        "Hàng sắp hết:\n"
        "Hàng gần hết hạn:\n"
        "Hàng hư hao / thất thoát:\n"
        "Chi phí nhập hàng trong tuần:\n"
        "Vấn đề phát sinh:\n"
        "Đề xuất xử lý tuần tới:\n"
        "Người duyệt: Miss Uyên\n"
        "Ghi chú:"
    )
def main() -> None:
    if not TOKEN:
        raise RuntimeError("Thiếu BOT_TOKEN. Hãy thêm biến môi trường BOT_TOKEN trên Render.")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getchatid", getchatid_cmd))
    app.add_handler(CommandHandler("linkshiftgroup", linkshiftgroup_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addat", addat))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("remove", remove_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("tonkho", tonkho_cmd))
    app.add_handler(CommandHandler("khohelp", khohelp_cmd))
    app.add_handler(CommandHandler("nhaphang", nhaphang_cmd))
    app.add_handler(CommandHandler("thieuhang", thieuhang_cmd))
    app.add_handler(CommandHandler("xuatkho", xuatkho_cmd))
    app.add_handler(CommandHandler("kiemkho", kiemkho_cmd))
    app.add_handler(CommandHandler("baocaokho", baocaokho_cmd))
    app.add_handler(CommandHandler("baocaokhotuan", baocaokhotuan_cmd))
    app.add_handler(CommandHandler("now", now_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(CommandHandler("todaywork", todaywork_cmd))
    app.add_handler(CommandHandler("timesheet", timesheet_cmd))     
    app.add_handler(CommandHandler("payrollweek", payrollweek_cmd))
    app.add_handler(CommandHandler("payrollmonth", payrollmonth_cmd))
    app.add_handler(CommandHandler("payrollfinal", payrollfinal_cmd))
    app.add_handler(CommandHandler("payrolllock", payrolllock_cmd))
    app.add_handler(CommandHandler("payrollunlock", payrollunlock_cmd))
    app.add_handler(CommandHandler("payslip", payslip_cmd))
    app.add_handler(CommandHandler("clearattendance", clearattendance_cmd))
    app.add_handler(CommandHandler("salarytype", salarytype_cmd))
    app.add_handler(CommandHandler("sethourly", sethourly_cmd))
    app.add_handler(CommandHandler("fixedsalary", fixedsalary_cmd))
    app.add_handler(CommandHandler("bonus", bonus_cmd))
    app.add_handler(CommandHandler("bonusremove", bonusremove_cmd))
    app.add_handler(CommandHandler("advance", advance_cmd))
    app.add_handler(CommandHandler("fine", fine_cmd))
    app.add_handler(CommandHandler("fineremove", fineremove_cmd))
    app.add_handler(CommandHandler("finelist", finelist_cmd))
    app.add_handler(CommandHandler("resetpayroll", resetpayroll_cmd))
    app.add_handler(CommandHandler("salarylist", salarylist_cmd))
    app.add_handler(CommandHandler("payrollsummary", payrollsummary_cmd))
    app.add_handler(CommandHandler("payrollexport", payrollexport_cmd))
    app.add_handler(CommandHandler("payrollweek", payrollweek_cmd))
    app.add_handler(CommandHandler("fixcheckin", fixcheckin_cmd))
    app.add_handler(CommandHandler("fixcheckout", fixcheckout_cmd))
    app.add_handler(CommandHandler("addmonthly", addmonthly_cmd))
    app.add_handler(CommandHandler("monthlylist", monthlylist_cmd))
    app.add_handler(CommandHandler("removemonthly", removemonthly_cmd))
    app.add_handler(CommandHandler("addlunar", addlunar_cmd))
    app.add_handler(CommandHandler("lunarlist", lunarlist_cmd))
    app.add_handler(CommandHandler("removelunar", removelunar_cmd))
    app.add_handler(CommandHandler("addbirthday", addbirthday_cmd))
    app.add_handler(CommandHandler("birthdaylist", birthdaylist_cmd))
    app.add_handler(CommandHandler("removebirthday", removebirthday_cmd))
    app.add_handler(CommandHandler("checkshift", checkshift_cmd))
    app.add_handler(CommandHandler("staffadd", staffadd_cmd))
    app.add_handler(CommandHandler("staffremove", staffremove_cmd))
    app.add_handler(CommandHandler("stafflist", stafflist_cmd))
    app.add_handler(CommandHandler("revenue", revenue_cmd))
    app.add_handler(CommandHandler("revenuelist", revenuelist_cmd))
    app.add_handler(CommandHandler("revenueweek", revenueweek_cmd))
    app.add_handler(CommandHandler("revenuemonth", revenuemonth_cmd))
    app.add_handler(CommandHandler("revenuedashboard", revenuedashboard_cmd))
    app.add_handler(CommandHandler("income", income_cmd))
    app.add_handler(CommandHandler("expense", expense_cmd))
    app.add_handler(CommandHandler("thu", incomelist_cmd))
    app.add_handler(CommandHandler("expenselist", expenselist_cmd))
    app.add_handler(CommandHandler("pl", pl_cmd))
    app.add_handler(CommandHandler("financeweek", financeweek_cmd))
    app.add_handler(CommandHandler("financemonth", financemonth_cmd))
    app.add_handler(CommandHandler("resetfinance", resetfinance_cmd))
    app.add_handler(CommandHandler("plmonth", plmonth_cmd))
    app.add_handler(CommandHandler("paymentrequest", paymentrequest_cmd))
    app.add_handler(CommandHandler("paymentlist", paymentlist_cmd))
    app.add_handler(CommandHandler("paymentdetail", paymentdetail_cmd))
    app.add_handler(CommandHandler("paymentpending", paymentpending_cmd))
    app.add_handler(CommandHandler("paymentapprove", paymentapprove_cmd))
    app.add_handler(CommandHandler("paymentreject", paymentreject_cmd))
    app.add_handler(CommandHandler("paymentpaid", paymentpaid_cmd))
    app.add_handler(CommandHandler("paymentreport", paymentreport_cmd))
    app.add_handler(CommandHandler("shift", shift_cmd))
    app.add_handler(CommandHandler("week", week_cmd))
    app.add_handler(CommandHandler("ranh", ranh_cmd))
    app.add_handler(CommandHandler("checkranh", checkranh_cmd))
    app.add_handler(CommandHandler("xepca", xepca_cmd))
    app.add_handler(CommandHandler("lich", lich_cmd))
    app.add_handler(CommandHandler("xoaca", xoaca_cmd))
    app.add_handler(CommandHandler("tonggio", tonggio_cmd))
    app.add_handler(CommandHandler("thieuca", thieuca_cmd))
    app.add_handler(CommandHandler("doica", doica_cmd))
    app.add_handler(CommandHandler("duyetca", duyetca_cmd))
    app.add_handler(CommandHandler("scanthieuca", scanthieuca_cmd))
    app.add_handler(CommandHandler("chotlich", chotlich_cmd))
    app.add_handler(CommandHandler("canhan", canhan_cmd))
    app.add_handler(CommandHandler("nhanvien", nhanvien_cmd))
    app.add_handler(CommandHandler("canhdong", canhdong_cmd))
    app.add_handler(CommandHandler("clearshift", clearshift_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_done))
    schedule_all(app)
    schedule_lunar_all(app)
    schedule_birthday_all(app)
    schedule_monthly_all(app)

    log.info("Bot TF PRO starting in timezone %s", TZ_NAME)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
