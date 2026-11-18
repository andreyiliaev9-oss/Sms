# panel_buttons.py — бот-пульт с инлайн-кнопками
# Python 3.10+, python-telegram-bot>=20.7, aiohttp
import logging
import os
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("TG_BOT_TOKEN", "8993557899:AAFCg3iQDoeO9NMbKnBcMVk6W50HC5C4CWA")
ADMIN_ID = 8141670312
API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8080")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

def get_main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📊 Статус / Метрики", callback_data="menu_metrics")],
        [InlineKeyboardButton("🚀 Запустить (одиночный)", callback_data="menu_single"),
         InlineKeyboardButton("🔄 Ротация (multi)", callback_data="menu_multi")],
        [InlineKeyboardButton("🛑 СТОП", callback_data="menu_stop")],
        [InlineKeyboardButton("🛠 Чистка / Maint", callback_data="menu_maint")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def _api_post(endpoint: str, json_data: dict = None) -> str:
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{API_BASE}/{endpoint}", json=json_data) as r:
            return await r.text()

async def _api_get(endpoint: str) -> str:
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{API_BASE}/{endpoint}") as r:
            return await r.text()

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("нет доступа")
        return
    await update.message.reply_text(
        "🎛 **Главное меню управления**\nВыбери действие:",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("нет доступа")
        return

    await query.answer()
    data = query.data

    if data == "menu_main":
        await query.edit_message_text("🎛 **Главное меню**", reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "menu_metrics":
        res = await _api_get("metrics")
        text = f"📊 **Метрики:**\n```json\n{res[:3800]}\n```"
        kb = [[InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "menu_stop":
        res = await _api_post("stop")
        kb = [[InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]]
        await query.edit_message_text(f"🛑 **Движок остановлен**\n{res}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "menu_maint":
        res = await _api_post("maintenance")
        kb = [[InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]]
        await query.edit_message_text(f"🛠 **Обслуживание выполнено**\n{res}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "menu_single":
        text = "Введи номер для одиночного прогона:\n`/single 79991234567 10`"
        kb = [[InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "menu_multi":
        text = "Введи номера для ротации:\n`/multi 79991234567:10 79987654321:5`"
        kb = [[InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# Команды для ввода данных
async def cmd_single(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not ctx.args:
        await update.message.reply_text("формат: /single <phone> [rounds]")
        return
    phone = ctx.args[0]
    rounds = int(ctx.args[1]) if len(ctx.args) > 1 and ctx.args[1].isdigit() else 10
    await update.message.reply_text(f"🚀 Запускаю: {phone} x{rounds}")
    res = await _api_post("start", {"phone": phone, "rounds": rounds})
    await update.message.reply_text(f"Результат: {res}", reply_markup=get_main_menu())

async def cmd_multi(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    targets = []
    for a in ctx.args:
        if ":" in a:
            phone, r = a.split(":", 1)
            if phone.lstrip("+").isdigit() and r.isdigit():
                targets.append({"phone": phone, "rounds": int(r)})
    if not targets:
        await update.message.reply_text("формат: /multi 7999...:10 7998...:5")
        return
    await update.message.reply_text(f"🔄 Запускаю ротацию: {len(targets)} целей")
    res = await _api_post("multi", {"targets": targets})
    await update.message.reply_text(f"Результат: {res}", reply_markup=get_main_menu())

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("single", cmd_single))
    app.add_handler(CommandHandler("multi", cmd_multi))
    app.add_handler(CallbackQueryHandler(handle_callback))
    log.info("bot with buttons up")
    app.run_polling()

if __name__ == "__main__":
    main()
