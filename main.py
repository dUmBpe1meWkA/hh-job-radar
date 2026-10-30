from __future__ import annotations

import asyncio
import html
import secrets
import time
import traceback
from typing import Any

from aiohttp import web
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from config import config
from db import Database
from hh_api import HHApiError, HHClient
from letters import make_letter
from scoring import score_vacancy


db = Database(config.db_path)
hh_client = HHClient(db)


def allowed(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.id == config.telegram_chat_id)


def resume_id() -> str:
    return db.get_setting("resume_id", config.hh_resume_id)


def fmt_salary(v: dict[str, Any]) -> str:
    salary = v.get("salary") or {}
    if not salary:
        return "не указана"
    currency = salary.get("currency") or ""
    frm = salary.get("from")
    to = salary.get("to")
    if frm and to:
        return f"{frm:,}–{to:,} {currency}".replace(",", " ")
    if frm:
        return f"от {frm:,} {currency}".replace(",", " ")
    if to:
        return f"до {to:,} {currency}".replace(",", " ")
    return "не указана"


def vacancy_message(row) -> str:
    raw = {}
    try:
        import json
        raw = json.loads(row["raw_json"] or "{}")
    except Exception:
        raw = {}

    title = html.escape(row["title"])
    company = html.escape(row["company"] or "")
    url = html.escape(row["url"] or "")
    reason = html.escape(row["reason"] or "")
    area = html.escape(((raw.get("area") or {}).get("name") or ""))
    experience = html.escape(((raw.get("experience") or {}).get("name") or ""))
    employment = html.escape(((raw.get("employment") or {}).get("name") or ""))
    schedule = html.escape(((raw.get("schedule") or {}).get("name") or ""))
    has_test = raw.get("test") and raw.get("test", {}).get("required")
    letter_required = raw.get("response_letter_required")

    flags = []
    if has_test:
        flags.append("⚠️ есть обязательный тест")
    if letter_required:
        flags.append("✉️ письмо обязательно")
    flags_text = "\n" + "\n".join(flags) if flags else ""

    return (
        f"🔥 <b>{row['score']}/100 — {title}</b>\n\n"
        f"<b>Компания:</b> {company}\n"
        f"<b>Город:</b> {area}\n"
        f"<b>Опыт:</b> {experience}\n"
        f"<b>Занятость:</b> {employment}\n"
        f"<b>График:</b> {schedule}\n"
        f"<b>Зарплата:</b> {html.escape(fmt_salary(raw))}{flags_text}\n\n"
        f"<b>Почему подходит:</b>\n{reason}\n\n"
        f"<a href=\"{url}\">Открыть вакансию на hh</a>"
    )


def vacancy_keyboard(row) -> InlineKeyboardMarkup:
    url = row["url"] or "https://hh.ru"
    vid = row["id"]
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Откликнуться", callback_data=f"apply:{vid}"),
             InlineKeyboardButton("📝 Письмо", callback_data=f"letter:{vid}")],
            [InlineKeyboardButton("🌐 Открыть HH", url=url),
             InlineKeyboardButton("🚫 Скрыть", callback_data=f"hide:{vid}")],
            [InlineKeyboardButton("☑️ Откликнулся вручную", callback_data=f"mark:{vid}")],
        ]
    )


async def send_vacancy(bot, row) -> None:
    await bot.send_message(
        chat_id=config.telegram_chat_id,
        text=vacancy_message(row),
        parse_mode=ParseMode.HTML,
        reply_markup=vacancy_keyboard(row),
        disable_web_page_preview=True,
    )
    db.mark_notified(row["id"])


async def scan_once(bot=None) -> tuple[int, int]:
    total_saved = 0
    for query in config.search_queries:
        for page in range(config.max_pages_per_query):
            try:
                data = await hh_client.search_vacancies(query, page=page)
            except Exception as exc:
                print(f"Search failed for {query=}, {page=}: {exc}")
                continue

            for item in data.get("items", []):
                try:
                    full = await hh_client.get_vacancy(str(item["id"]))
                    merged = {**item, **full}
                    score, reason = score_vacancy(merged)
                    letter = make_letter(merged)
                    is_new = db.upsert_vacancy(item=merged, score=score, reason=reason, letter=letter, raw=merged)
                    if is_new:
                        total_saved += 1
                except Exception as exc:
                    print(f"Vacancy processing failed: {item.get('id')}: {exc}")
                    continue

            # Do not hammer API.
            await asyncio.sleep(0.4)

    sent = 0
    if bot:
        for row in db.unseen_good_vacancies(config.min_score, limit=20):
            await send_vacancy(bot, row)
            sent += 1
            await asyncio.sleep(0.25)

    return total_saved, sent


async def scanner_loop(app: Application) -> None:
    await asyncio.sleep(5)
    while True:
        try:
            saved, sent = await scan_once(app.bot)
            print(f"Scan completed: saved={saved}, sent={sent}")
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(config.scan_interval_minutes * 60)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    await update.message.reply_text(
        "HH Job Radar запущен.\n\n"
        "Команды:\n"
        "/scan — найти вакансии сейчас\n"
        "/auth — подключить hh OAuth для отклика из Telegram\n"
        "/status — проверить подключение\n"
        "/set_resume <id> — задать ID резюме\n"
        "/help — справка"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    await cmd_start(update, context)


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    msg = await update.message.reply_text("Ищу свежие вакансии на hh...")
    saved, sent = await scan_once(context.bot)
    await msg.edit_text(f"Готово. Новых сохранено: {saved}. Отправлено в чат: {sent}.")


async def cmd_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    if not (config.hh_client_id and config.hh_client_secret and config.hh_redirect_uri):
        await update.message.reply_text(
            "Не заполнены HH_CLIENT_ID / HH_CLIENT_SECRET / HH_REDIRECT_URI в .env."
        )
        return
    state = secrets.token_urlsafe(24)
    db.set_setting("oauth_state", state)
    url = hh_client.auth_url(state)
    await update.message.reply_text(
        "Открой ссылку, войди в hh и разреши доступ. После редиректа сервер сохранит токен.\n\n"
        f"{url}"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    token = db.get_token()
    rid = resume_id()
    parts = []
    parts.append(f"Resume ID: {rid or 'не задан'}")
    if token:
        expires_in = int(token["expires_at"] or 0) - int(time.time())
        parts.append(f"HH OAuth: подключен, expires_in ≈ {max(0, expires_in // 60)} мин.")
        try:
            me = await hh_client.get_me()
            parts.append(f"HH user: {me.get('first_name', '')} {me.get('last_name', '')}".strip())
        except Exception as exc:
            parts.append(f"HH user check: ошибка {exc}")
    else:
        parts.append("HH OAuth: не подключен. Выполни /auth")
    await update.message.reply_text("\n".join(parts))


async def cmd_set_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    if not context.args:
        await update.message.reply_text("Формат: /set_resume <id_резюме>")
        return
    rid = context.args[0].strip()
    db.set_setting("resume_id", rid)
    await update.message.reply_text(f"Ок, Resume ID сохранён: {rid}")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    query = update.callback_query
    await query.answer()
    if not query.data or ":" not in query.data:
        return
    action, vacancy_id = query.data.split(":", 1)
    row = db.get_vacancy(vacancy_id)
    if not row:
        await query.edit_message_text("Вакансия не найдена в базе.")
        return

    if action == "letter":
        await context.bot.send_message(
            chat_id=config.telegram_chat_id,
            text=f"📝 Письмо для <b>{html.escape(row['title'])}</b>:\n\n{html.escape(row['letter'])}",
            parse_mode=ParseMode.HTML,
        )
        return

    if action == "hide":
        db.hide_vacancy(vacancy_id)
        await query.edit_message_text(f"Скрыто: {row['title']}")
        return

    if action == "mark":
        db.mark_applied(vacancy_id)
        await query.edit_message_text(f"Отмечено как отклик: {row['title']}")
        return

    if action == "apply":
        rid = resume_id()
        if not rid:
            await context.bot.send_message(
                chat_id=config.telegram_chat_id,
                text="Не задан ID резюме. Используй /set_resume <id> или HH_RESUME_ID в .env.",
            )
            return
        await context.bot.send_message(
            chat_id=config.telegram_chat_id,
            text=f"Пробую откликнуться на: {row['title']}...",
        )
        try:
            await hh_client.apply(vacancy_id=vacancy_id, resume_id=rid, message=row["letter"])
            db.mark_applied(vacancy_id)
            await context.bot.send_message(
                chat_id=config.telegram_chat_id,
                text=f"✅ Отклик отправлен: {row['title']}",
            )
        except HHApiError as exc:
            payload = exc.payload
            error_text = html.escape(str(payload))
            if "already_applied" in str(payload):
                db.mark_applied(vacancy_id)
                await context.bot.send_message(
                    chat_id=config.telegram_chat_id,
                    text=f"☑️ На эту вакансию уже был отклик: {html.escape(row['title'])}",
                    parse_mode=ParseMode.HTML,
                )
            elif "test_required" in str(payload):
                await context.bot.send_message(
                    chat_id=config.telegram_chat_id,
                    text=(
                        "⚠️ Через API нельзя откликнуться, потому что у вакансии обязательный тест. "
                        f"Открой вручную: {row['url']}"
                    ),
                )
            else:
                await context.bot.send_message(
                    chat_id=config.telegram_chat_id,
                    text=f"❌ HH API вернул ошибку {exc.status_code}:\n<code>{error_text}</code>\n\nСсылка: {html.escape(row['url'])}",
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
        except Exception as exc:
            await context.bot.send_message(
                chat_id=config.telegram_chat_id,
                text=f"❌ Ошибка отклика: {exc}",
            )


async def hh_callback(request: web.Request) -> web.Response:
    code = request.query.get("code", "")
    state = request.query.get("state", "")
    expected = db.get_setting("oauth_state", "")
    if not code:
        return web.Response(text="No code in callback", status=400)
    if not expected or state != expected:
        return web.Response(text="Bad state", status=403)
    try:
        await hh_client.exchange_code(code)
    except Exception as exc:
        return web.Response(text=f"OAuth error: {exc}", status=500)
    return web.Response(text="HH OAuth подключен. Можно вернуться в Telegram и выполнить /status.")


async def start_web_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/hh/callback", hh_callback)
    app.router.add_get("/health", lambda request: web.Response(text="ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=config.oauth_host, port=config.oauth_port)
    await site.start()
    print(f"OAuth callback server started on {config.oauth_host}:{config.oauth_port}")
    return runner


async def main() -> None:
    if not config.telegram_bot_token or not config.telegram_chat_id:
        raise RuntimeError("Fill TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")

    app = Application.builder().token(config.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("auth", cmd_auth))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("set_resume", cmd_set_resume))
    app.add_handler(CallbackQueryHandler(on_callback))

    runner = await start_web_server()
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    asyncio.create_task(scanner_loop(app))

    print("Telegram bot started")
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
