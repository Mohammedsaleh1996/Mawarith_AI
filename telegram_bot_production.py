# -*- coding: utf-8 -*-
"""
Telegram bot wrapper for Mawareth AI Runtime v8.
Requirements:
  pip install python-telegram-bot==21.6
Environment:
  set TELEGRAM_BOT_TOKEN=YOUR_TOKEN
Run:
  python telegram_bot_production.py
"""
from __future__ import annotations
import os, sys, json, time, uuid
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

HERE = Path(__file__).resolve().parent
from mawarith_ai_runtime_v9 import answer, normalize_ar, detect_concept_key  # noqa

LOG_DIR = HERE / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "telegram_requests.jsonl"
SESSION_CONTEXTS: dict[str, dict] = {}


def append_log(record: dict) -> None:
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أرسل مسألة ميراث أو سؤالًا فقهيًا في المواريث. لو السؤال ناقص سأطلب توضيحًا بدل التخمين.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.message.text or ""
    request_id = str(uuid.uuid4())
    t0 = time.time()
    uid = str(update.effective_user.id) if update.effective_user else "anonymous"
    context_state = SESSION_CONTEXTS.get(uid, {})
    ans = answer(q, context=context_state)
    try:
        SESSION_CONTEXTS[uid] = {
            "last_question": q,
            "last_answer": ans,
            "last_concept": detect_concept_key(q) or context_state.get("last_concept"),
        }
    except Exception:
        pass
    elapsed_ms = int((time.time() - t0) * 1000)
    append_log({
        "request_id": request_id,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "telegram_user_id": update.effective_user.id if update.effective_user else None,
        "question": q,
        "answer": ans,
        "elapsed_ms": elapsed_ms,
    })
    # Telegram message limit safety
    for i in range(0, len(ans), 3900):
        await update.message.reply_text(ans[i:i+3900])


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
