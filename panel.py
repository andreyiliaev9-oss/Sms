# panel.py — бот-нотифаер: дёргает API
# Python 3.10+, python-telegram-bot>=20.7, aiohttp
import logging
import os
import subprocess

import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("TG_BOT_TOKEN", "8993557899:AAFCg3iQDoeO9NMbKnBcMVk6W50HC5C4CWA")
ADMIN_ID = 8141670312
API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8080")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")


def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


async def remote_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("нет доступа")
        return
    if not ctx.args:
        await update.message.reply_text("формат: /start <phone> [rounds]")
        return
    phone = ctx.args[0]
    rounds = int(ctx.args[1]) if len(ctx.args) > 1 and ctx.args[1].isdigit() else 10
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{API_BASE}/start", json={"phone": phone, "rounds": rounds}) as r:
            await update.message.reply_text(f"api: {await r.text()}")


async def remote_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("нет доступа")
        return
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{API_BASE}/stop") as r:
            await update.message.reply_text(f"api: {await r.text()}")


async def remote_metrics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("нет доступа")
        return
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{API_BASE}/metrics") as r:
            await update.message.reply_text((await r.text())[:3800])


async def remote_multi(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("нет доступа")
        return
    targets = []
    for a in ctx.args:
        if ":" in a:
            phone, r = a.split(":", 1)
            if phone.lstrip("+").isdigit() and r.isdigit():
                targets.append({"phone": phone, "rounds": int(r)})
    if not targets:
        await update.message.reply_text("формат: /multi 7999...:10 7998...:5")
        return
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{API_BASE}/multi", json={"targets": targets}) as r:
            await update.message.reply_text(f"api: {await r.text()}")


async def cmd_purge(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("нет доступа")
        return
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{API_BASE}/purge") as r:
            await update.message.reply_text(f"purge: {await r.text()}")


async def cmd_dropped(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("нет доступа")
        return
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{API_BASE}/dropped") as r:
            await update.message.reply_text(f"dropped: {await r.text()}")


async def cmd_drop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("нет доступа")
        return
    if not ctx.args:
        await update.message.reply_text("формат: /drop <name>")
        return
    name = ctx.args[0]
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{API_BASE}/drop/{name}") as r:
            await update.message.reply_text(f"drop: {await r.text()}")


async def cmd_maint(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("нет доступа")
        return
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{API_BASE}/maintenance") as r:
            await update.message.reply_text(f"maint: {await r.text()}")


async def cmd_backup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("нет доступа")
        return
    try:
        out = subprocess.check_output(
            ["bash", "/app/backup.sh"], text=True, timeout=30)
        await update.message.reply_text(f"backup:\n{out[:3800]}")
    except subprocess.CalledProcessError as e:
        await update.message.reply_text(f"ошибка: {e}")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("команды: /start /stop /multi /metrics /registry /drop /dropped /purge /maint /backup")


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", remote_start))
    app.add_handler(CommandHandler("stop", remote_stop))
    app.add_handler(CommandHandler("metrics", remote_metrics))
    app.add_handler(CommandHandler("multi", remote_multi))
    app.add_handler(CommandHandler("purge", cmd_purge))
    app.add_handler(CommandHandler("dropped", cmd_dropped))
    app.add_handler(CommandHandler("drop", cmd_drop))
    app.add_handler(CommandHandler("maint", cmd_maint))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    log.info("bot up")
    app.run_polling()


if __name__ == "__main__":
    main()
