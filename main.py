import os
import json
import logging
from pathlib import Path
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from lunardate import LunarDate
from typing import Dict, List, Any

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
            raise ValueError(f"Ngày không hợp lệ: {d}. Dùng mon,tue,wed,thu,fri,sat,sun hoặc daily/weekdays/weekends.")
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
        "/list\n/remove <số>\n/clear\n/now\n/help"
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
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    text_upper = text.upper()
    chat_id = str(update.effective_chat.id)
    today_key = datetime.now(TZ).strftime("%Y-%m-%d")
    now = datetime.now(TZ).strftime("%H:%M")

    if text_upper.startswith("CHECKIN"):
        staff_name = text.split("-", 1)[1].strip() if "-" in text else text[7:].strip()
        staff_list = DATA.get("staff", {}).get(chat_id, [])

        if not staff_name:
            await update.message.reply_text("❌ Vui lòng ghi đúng: CHECKIN Tên")
            return

        if staff_list and staff_name not in staff_list:
            await update.message.reply_text(
                f"❌ Tên nhân viên chưa có trong danh sách: {staff_name}\n"
                "Dùng /stafflist để xem tên hợp lệ."
            )
            return

        DATA.setdefault("attendance", {}).setdefault(chat_id, {}).setdefault(today_key, {}).setdefault(staff_name, {})
        DATA["attendance"][chat_id][today_key][staff_name]["checkin"] = now
        save_data(DATA)

        await update.message.reply_text(
            f"✅ Đã ghi nhận CHECKIN: {staff_name} lúc {now}"
        )
        return

    if text_upper.startswith("CHECKOUT"):
        staff_name = text.split("-", 1)[1].strip() if "-" in text else text[8:].strip()
        staff_list = DATA.get("staff", {}).get(chat_id, [])

        if not staff_name:
            await update.message.reply_text("❌ Vui lòng ghi đúng: CHECKOUT Tên")
            return

        if staff_list and staff_name not in staff_list:
            await update.message.reply_text(
                f"❌ Tên nhân viên chưa có trong danh sách: {staff_name}\n"
                "Dùng /stafflist để xem tên hợp lệ."
            )
            return

        DATA.setdefault("attendance", {}).setdefault(chat_id, {}).setdefault(today_key, {}).setdefault(staff_name, {})
        DATA["attendance"][chat_id][today_key][staff_name]["checkout"] = now
        save_data(DATA)

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
    chat_id = str(update.effective_chat.id)
    attendance_all = DATA.get("attendance", {}).get(chat_id, {})

    if not attendance_all:
        await update.message.reply_text("📊 Chưa có dữ liệu chấm công.")
        return

    recent_days = sorted(attendance_all.keys())[-7:]
    lines = ["📊 BẢNG CHẤM CÔNG 7 NGÀY GẦN ĐÂY", ""]

    for day_key in recent_days:
        lines.append(f"📅 {day_key}")
        day_data = attendance_all.get(day_key, {})

        for staff_name, record in day_data.items():
            checkin = record.get("checkin", "Chưa có")
            checkout = record.get("checkout", "Chưa có")

            lines.append(f"{staff_name}")
            lines.append(f"- CHECKIN: {checkin}")
            lines.append(f"- CHECKOUT: {checkout}")
            lines.append("")

    await update.message.reply_text("\n".join(lines))
async def staffadd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    staff_name = " ".join(context.args).strip()

    if not staff_name:
        await update.message.reply_text("❌ Cách dùng: /staffadd Tên nhân viên")
        return

    DATA.setdefault("staff", {}).setdefault(chat_id, [])

    if staff_name in DATA["staff"][chat_id]:
        await update.message.reply_text(f"⚠️ {staff_name} đã có trong danh sách nhân viên.")
        return

    DATA["staff"][chat_id].append(staff_name)
    save_data(DATA)

    await update.message.reply_text(f"✅ Đã thêm nhân viên: {staff_name}")


async def staffremove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    staff_name = " ".join(context.args).strip()

    if not staff_name:
        await update.message.reply_text("❌ Cách dùng: /staffremove Tên nhân viên")
        return

    staff_list = DATA.get("staff", {}).get(chat_id, [])

    if staff_name not in staff_list:
        await update.message.reply_text(f"⚠️ Không tìm thấy nhân viên: {staff_name}")
        return

    staff_list.remove(staff_name)
    save_data(DATA)

    await update.message.reply_text(f"✅ Đã xóa nhân viên: {staff_name}")


async def stafflist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    staff_list = DATA.get("staff", {}).get(chat_id, [])

    if not staff_list:
        await update.message.reply_text("📋 Chưa có nhân viên nào trong danh sách.")
        return

    lines = ["📋 DANH SÁCH NHÂN VIÊN TF", ""]

    for index, staff_name in enumerate(staff_list, start=1):
        lines.append(f"{index}. {staff_name}")

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
    chat_id = str(update.effective_chat.id)
    rate = 30000

    now_dt = datetime.now(TZ)
    attendance_all = DATA.get("attendance", {}).get(chat_id, {})

    totals = {}
    issues = []

    for i in range(7):
        day_dt = datetime.fromtimestamp(now_dt.timestamp() - i * 86400, TZ)
        day_key = day_dt.strftime("%Y-%m-%d")
        day_data = attendance_all.get(day_key, {})

        for staff_name, record in day_data.items():
            checkin = record.get("checkin")
            checkout = record.get("checkout")

            if not checkin or not checkout:
                issues.append(f"- {staff_name} ngày {day_key}: thiếu CHECKIN hoặc CHECKOUT")
                continue

            try:
                checkin_dt = datetime.strptime(checkin, "%H:%M")
                checkout_dt = datetime.strptime(checkout, "%H:%M")
                minutes = int((checkout_dt - checkin_dt).total_seconds() / 60)

                if minutes <= 0:
                    issues.append(f"- {staff_name} ngày {day_key}: giờ CHECKOUT không hợp lệ")
                    continue

                totals.setdefault(staff_name, 0)
                totals[staff_name] += minutes

            except Exception:
                issues.append(f"- {staff_name} ngày {day_key}: dữ liệu giờ không hợp lệ")

    lines = ["💰 BẢNG LƯƠNG TẠM 7 NGÀY GẦN ĐÂY", ""]

    if totals:
        for staff_name, minutes in totals.items():
            hours = minutes // 60
            mins = minutes % 60
            salary = round((minutes / 60) * rate)

            lines.append(f"👤 {staff_name}")
            lines.append(f"- Tổng giờ: {hours} giờ {mins} phút")
            lines.append(f"- Lương tạm: {salary:,}đ".replace(",", "."))
            lines.append("")
    else:
        lines.append("Chưa có dữ liệu đủ CHECKIN/CHECKOUT để tính lương.")
        lines.append("")

    if issues:
        lines.append("⚠️ Dữ liệu cần Mr.Win kiểm tra:")
        lines.extend(issues)

    await update.message.reply_text("\n".join(lines))
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

    now_dt = datetime.now(TZ)
    current_month = now_dt.strftime("%Y-%m")
    attendance_all = DATA.get("attendance", {}).get(chat_id, {})
    salary_data = DATA.get("salary", {}).get(chat_id, {})
    totals = {}
    issues = []

    for day_key, day_data in attendance_all.items():
        if not day_key.startswith(current_month):
            continue

        for staff_name, record in day_data.items():
            salary_type = salary_data.get(staff_name, {}).get("type", "hourly")
            if salary_type == "fixed":
                continue
            checkin = record.get("checkin")
            checkout = record.get("checkout")

            if not checkin or not checkout:
                issues.append(f"- {staff_name} ngày {day_key}: thiếu CHECKIN hoặc CHECKOUT")
                continue

            try:
                checkin_dt = datetime.strptime(checkin, "%H:%M")
                checkout_dt = datetime.strptime(checkout, "%H:%M")
                minutes = int((checkout_dt - checkin_dt).total_seconds() / 60)

                if minutes <= 0:
                    issues.append(f"- {staff_name} ngày {day_key}: giờ CHECKOUT không hợp lệ")
                    continue

                totals.setdefault(staff_name, 0)
                totals[staff_name] += minutes

            except Exception:
                issues.append(f"- {staff_name} ngày {day_key}: dữ liệu giờ không hợp lệ")

    lines = [f"💰 BẢNG LƯƠNG TẠM THÁNG {now_dt.strftime('%m/%Y')}", ""]
    fixed_staff = []
    for staff_name, info in salary_data.items():
        if info.get("type") == "fixed":
            fixed_salary = info.get("fixed_salary", 0)
            fixed_staff.append((staff_name, fixed_salary))
    if totals or fixed_staff:
        for staff_name, minutes in totals.items():
            hours = minutes // 60
            mins = minutes % 60
            salary = round((minutes / 60) * rate)

            lines.append(f"👤 {staff_name}")
            lines.append(f"- Tổng giờ: {hours} giờ {mins} phút")
            lines.append(f"- Lương tạm: {salary:,}đ".replace(",", "."))
            lines.append("")
        for staff_name, fixed_salary in fixed_staff:
            lines.append(f"👤 {staff_name}")
            lines.append("- Loại lương: Lương cứng")
            lines.append(f"- Lương tháng: {fixed_salary:,}đ".replace(",", "."))
            lines.append("- Ghi chú: CHECKIN / CHECKOUT dùng để theo dõi ngày công")
            lines.append("")
    else:
        lines.append("Chưa có dữ liệu đủ CHECKIN/CHECKOUT để tính lương tháng.")
        lines.append("")

    if issues:
        lines.append("⚠️ Dữ liệu cần Mr.Win kiểm tra:")
        lines.extend(issues)

    await update.message.reply_text("\n".join(lines))
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
    save_data(DATA)

    await update.message.reply_text(
        f"✅ Đã cập nhật lương cứng cho {staff_name}:\n"
        f"{amount:,}đ/tháng".replace(",", ".")
    )


async def salarylist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    salary_data = DATA.get("salary", {}).get(chat_id, {})

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
            lines.append("- Loại lương: Theo giờ")
            lines.append("- Mức: 30.000đ/giờ")

        lines.append("")

    await update.message.reply_text("\n".join(lines))
async def monthly_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    today = datetime.now(TZ)

    if today.day != data["day"]:
        return

    await context.bot.send_message(
        chat_id=data["chat_id"],
        text=(
            "🔔 NHẮC VIỆC HẰNG THÁNG\n\n"
            f"{data['text']}"
        )
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
    await update.message.reply_text(
        "📦 TF KHO & NHẬP HÀNG\n\n"
        "Chức năng kho hiện đang ở giai đoạn ghi nhận thủ công.\n\n"
        "Các lệnh đang dùng:\n\n"
        "📥 /nhaphang - Gửi mẫu nhập hàng\n"
        "⚠️ /thieuhang - Gửi mẫu báo thiếu hàng\n"
        "📋 /kiemkho - Gửi mẫu kiểm kho\n\n"
        "Lưu ý: Nhân viên điền đúng mẫu để Mr.Happy và Mr.Win dễ kiểm tra."
    )

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
    app.add_handler(CommandHandler("kiemkho", kiemkho_cmd))
    app.add_handler(CommandHandler("baocaokho", baocaokho_cmd))
    app.add_handler(CommandHandler("baocaokhotuan", baocaokhotuan_cmd))
    app.add_handler(CommandHandler("now", now_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(CommandHandler("todaywork", todaywork_cmd))
    app.add_handler(CommandHandler("timesheet", timesheet_cmd))     
    app.add_handler(CommandHandler("payrollweek", payrollweek_cmd))
    app.add_handler(CommandHandler("payrollmonth", payrollmonth_cmd))
    app.add_handler(CommandHandler("clearattendance", clearattendance_cmd))
    app.add_handler(CommandHandler("salarytype", salarytype_cmd))
    app.add_handler(CommandHandler("fixedsalary", fixedsalary_cmd))
    app.add_handler(CommandHandler("salarylist", salarylist_cmd))
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
    app.add_handler(CommandHandler("shift", shift_cmd))
    app.add_handler(CommandHandler("week", week_cmd))
    app.add_handler(CommandHandler("clearshift", clearshift_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_done))
    schedule_all(app)
    schedule_lunar_all(app)
    schedule_birthday_all(app)
    log.info("Bot TF PRO starting in timezone %s", TZ_NAME)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
