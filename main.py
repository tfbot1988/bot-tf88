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
async def handle_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

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
def main() -> None:
    if not TOKEN:
        raise RuntimeError("Thiếu BOT_TOKEN. Hãy thêm biến môi trường BOT_TOKEN trên Render.")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addat", addat))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("remove", remove_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("now", now_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(CommandHandler("shift", shift_cmd))
    app.add_handler(CommandHandler("week", week_cmd))
    app.add_handler(CommandHandler("clearshift", clearshift_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_done))
    schedule_all(app)
    
    log.info("Bot TF PRO starting in timezone %s", TZ_NAME)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
