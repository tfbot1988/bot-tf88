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

async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    chat_id = job.data["chat_id"]
    text = job.data["text"]
    today = datetime.now(TZ).weekday()
    if today not in job.data.get("days", []):
        return
    await context.bot.send_message(chat_id=chat_id, text=f"⏰ {text}")
def clear_jobs_for_chat(app: Application, chat_id: str) -> None:
    for job in app.job_queue.jobs():
        if job.name.startswith(f"reminder:{chat_id}:"):
            job.schedule_removal()

def schedule_chat(app: Application, chat_id: str) -> None:
    clear_jobs_for_chat(app, chat_id)
    reminders = DATA.get("chats", {}).get(chat_id, [])
    for idx, item in enumerate(reminders, start=1):
        for time_str in item["times"]:
            hh, mm = map(int, time_str.split(":"))
            for d in item["days"]:
                app.job_queue.run_daily(
                    send_reminder,
                    time=time(hour=hh, minute=mm, tzinfo=TZ),
                    
                    data={"chat_id": int(chat_id), "text": item["text"], "days": item["days"]},
                    name=f"reminder:{chat_id}:{idx}:{time_str}:{d}",
                )

def schedule_all(app: Application) -> None:
    for chat_id in DATA.get("chats", {}):
        schedule_chat(app, chat_id)
    total = sum(len(v) for v in DATA.get("chats", {}).values())
    log.info("Scheduled %s reminder items across %s chats", total, len(DATA.get("chats", {})))

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
    schedule_all(app)
    log.info("Bot TF PRO starting in timezone %s", TZ_NAME)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
