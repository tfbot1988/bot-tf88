import os
import json
import logging
from pathlib import Path
from datetime import datetime, time
from zoneinfo import ZoneInfo
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

    if text_upper.startswith("CHECKIN"):
        staff_name = text.split("-", 1)[1].strip() if "-" in text else text[7:].strip()
        staff_list = DATA.get("staff", {}).get(str(update.effective_chat.id), [])
        if staff_list and staff_name not in staff_list:
            await update.message.reply_text(
                f"❌ Tên nhân viên chưa có trong danh sách: {staff_name}\n"
                "Dùng /stafflist để xem tên hợp lệ."
            )
            return
        if not staff_name:
            await update.message.reply_text("❌ Vui lòng ghi đúng: CHECKIN - Tên")
            return

        now = datetime.now(TZ).strftime("%H:%M")
        chat_id = str(update.effective_chat.id)
        today_key = datetime.now(TZ).strftime("%Y-%m-%d")

        DATA.setdefault("attendance", {}).setdefault(chat_id, {}).setdefault(today_key, {}).setdefault(staff_name, {})
        DATA["attendance"][chat_id][today_key][staff_name]["checkin"] = now
        save_data(DATA)

        await update.message.reply_text(
            f"✅ Đã ghi nhận CHECKIN: {staff_name} lúc {now}"
        )
        return

    if text_upper.startswith("CHECKOUT"):
        staff_name = text.split("-", 1)[1].strip() if "-" in text else text[8:].strip()
        staff_list = DATA.get("staff", {}).get(str(update.effective_chat.id), [])
        if staff_list and staff_name not in staff_list:
            await update.message.reply_text(
                f"❌ Tên nhân viên chưa có trong danh sách: {staff_name}\n"
                "Dùng /stafflist để xem tên hợp lệ."
            )
            return
        if not staff_name:
            await update.message.reply_text("❌ Vui lòng ghi đúng: CHECKOUT - Tên")
            return

        now = datetime.now(TZ).strftime("%H:%M")
        chat_id = str(update.effective_chat.id)
        today_key = datetime.now(TZ).strftime("%Y-%m-%d")

        DATA.setdefault("attendance", {}).setdefault(chat_id, {}).setdefault(today_key, {}).setdefault(staff_name, {})
        DATA["attendance"][chat_id][today_key][staff_name]["checkout"] = now
        save_data(DATA)

        await update.message.reply_text(
            f"✅ Đã ghi nhận CHECKOUT: {staff_name} lúc {now}"
        )
        return
    if not text.upper().startswith("DONE "):
        return

    body = text[5:].strip()

    if " - " in body:
        task_name, staff_name = body.split(" - ", 1)
    else:
        task_name = body
        staff_name = update.effective_user.first_name or "Nhân viên"

    task_name = task_name.strip()
    staff_name = staff_name.strip()
    now = datetime.now(TZ).strftime("%H:%M")
    chat_id = str(update.effective_chat.id)
    today_key = datetime.now(TZ).strftime("%Y-%m-%d")
    done_key = task_name.upper()
    reminders = DATA.get("chats", {}).get(chat_id, [])
    today = datetime.now(TZ).weekday()

    expected_keys = []
    for item in reminders:
        if today not in item.get("days", []):
            continue

        reminder_text = item.get("text", "")
        expected_key = extract_done_key(reminder_text)

        if expected_key:
            expected_keys.append(expected_key)

    if expected_keys and done_key not in expected_keys:
        await update.message.reply_text(
            "❌ Tên việc chưa đúng với lịch nhắc hôm nay.\n\n"
            "Vui lòng copy đúng phần sau chữ:\n"
            "Xong reply: DONE ... - Tên\n\n"
            "Các việc hợp lệ hôm nay:\n"
            + "\n".join([f"- DONE {key} - Tên" for key in expected_keys])
        )
        return
    DATA.setdefault("done", {}).setdefault(chat_id, {}).setdefault(today_key, {})
    DATA["done"][chat_id][today_key][done_key] = {
        "staff": staff_name,
        "time": now,
    }
    save_data(DATA)
    await update.message.reply_text(
        f"✅ Đã ghi nhận: {staff_name} hoàn thành {task_name} lúc {now}"
    )
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
    app.add_handler(CommandHandler("now", now_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(CommandHandler("todaywork", todaywork_cmd))
    app.add_handler(CommandHandler("timesheet", timesheet_cmd))     
    app.add_handler(CommandHandler("payrollweek", payrollweek_cmd))
    app.add_handler(CommandHandler("checkshift", checkshift_cmd))
    app.add_handler(CommandHandler("staffadd", staffadd_cmd))
    app.add_handler(CommandHandler("staffremove", staffremove_cmd))
    app.add_handler(CommandHandler("stafflist", stafflist_cmd))
    app.add_handler(CommandHandler("shift", shift_cmd))
    app.add_handler(CommandHandler("week", week_cmd))
    app.add_handler(CommandHandler("clearshift", clearshift_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_done))
    schedule_all(app)
    
    log.info("Bot TF PRO starting in timezone %s", TZ_NAME)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
