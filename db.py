"""
SCAM Tip Bot — телеграм-бот для перевода внутренних токенов SCAM.

Как пользоваться:
  Ответьте (reply) на сообщение пользователя и напишите:  пер 0,048
  Бот переведёт 0,048 SCAM автору того сообщения и пришлёт картинку:
    сверху крупно — 0,048
    снизу — «#SCAM отправил(а) 0,048 SCAM для @user»

Команды:
  /start   — приветствие и справка
  /balance — ваш баланс SCAM
  /top     — топ держателей SCAM
  /give    — (только админ) начислить SCAM: reply + «/give 100»

ВАЖНО: SCAM здесь — это внутренние очки, которые бот хранит в своей базе.
Это НЕ криптовалюта в блокчейне и реальные монеты никуда не уходят.
"""

import asyncio
import logging
import os
import re
from decimal import Decimal, InvalidOperation

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, Message

import db
from image_gen import render_transfer_image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("scam-bot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN (переменная окружения).")

# id админов через запятую, напр. ADMIN_IDS="12345,67890"
ADMIN_IDS = {
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x
}

# Триггер перевода: «пер 0,048», «пер 12», «пер 3.5». Регистр не важен.
TRANSFER_RE = re.compile(r"^\s*пер\s+(\d+(?:[.,]\d+)?)\s*$", re.IGNORECASE)

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def _user_dict(u) -> dict:
    return {"id": u.id, "username": u.username, "first_name": u.first_name}


def _display_name(u) -> str:
    """Как показать пользователя: @username, иначе имя."""
    if getattr(u, "username", None):
        return f"@{u.username}"
    return (getattr(u, "first_name", None) or "пользователь")


def _parse_amount(raw: str) -> Decimal:
    """'0,048' -> Decimal('0.048')."""
    return Decimal(raw.replace(",", "."))


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 <b>SCAM Tip Bot</b>\n\n"
        "Чтобы перевести SCAM — <b>ответьте</b> на сообщение человека и напишите:\n"
        "<code>пер 0,048</code>\n\n"
        "Я переведу ему токены и пришлю красивую картинку 🖼️\n\n"
        "Команды:\n"
        "• /balance — ваш баланс\n"
        "• /top — топ держателей\n\n"
        "<i>SCAM — внутренние очки бота, не криптовалюта.</i>"
    )


@dp.message(Command("balance"))
async def cmd_balance(message: Message) -> None:
    u = message.from_user
    bal = await db.get_balance(u.id, u.username, u.first_name)
    await message.answer(f"💰 Ваш баланс: <b>{_fmt(bal)}</b> SCAM")


@dp.message(Command("top"))
async def cmd_top(message: Message) -> None:
    users = await db.get_top(10)
    if not users:
        await message.answer("Пока пусто 🤷")
        return
    lines = ["🏆 <b>Топ держателей SCAM</b>\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, u in enumerate(users):
        name = f"@{u.username}" if u.username else (u.first_name or f"id{u.id}")
        prefix = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{prefix} {name} — {_fmt(u.balance)} SCAM")
    await message.answer("\n".join(lines))


@dp.message(Command("give"))
async def cmd_give(message: Message) -> None:
    """Админская выдача: reply на пользователя + «/give 100»."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Команда только для администраторов.")
        return
    if not message.reply_to_message:
        await message.answer("Ответьте на сообщение пользователя, которому начислить.")
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Формат: <code>/give 100</code> в ответ на сообщение.")
        return
    try:
        amount = _parse_amount(parts[1])
    except (InvalidOperation, ValueError):
        await message.answer("Не понял сумму. Пример: <code>/give 100</code>")
        return

    target = message.reply_to_message.from_user
    # начисляем «из воздуха»: переводим сами себе-администратору не нужно —
    # просто увеличим баланс через транзакцию give
    from decimal import Decimal as D  # локальный импорт для наглядности

    async with db.Session() as session:
        async with session.begin():
            user = await db.get_or_create_user(
                session, target.id, target.username, target.first_name
            )
            user.balance = user.balance + amount
            new_bal = user.balance
    await message.answer(
        f"✅ Начислено {_fmt(amount)} SCAM для {_display_name(target)}. "
        f"Баланс: {_fmt(new_bal)} SCAM."
    )


@dp.message(F.text.regexp(TRANSFER_RE.pattern))
async def handle_transfer(message: Message) -> None:
    match = TRANSFER_RE.match(message.text or "")
    if not match:
        return

    # Должен быть reply на чьё-то сообщение
    if not message.reply_to_message:
        await message.reply(
            "Чтобы перевести SCAM, <b>ответьте</b> на сообщение получателя "
            "и напишите <code>пер 0,048</code>."
        )
        return

    sender = message.from_user
    recipient = message.reply_to_message.from_user

    if recipient.is_bot:
        await message.reply("🤖 Ботам SCAM не переводим.")
        return

    raw_amount = match.group(1)
    try:
        amount = _parse_amount(raw_amount)
    except (InvalidOperation, ValueError):
        await message.reply("Не понял сумму. Пример: <code>пер 0,048</code>")
        return

    try:
        sender_bal, _ = await db.do_transfer(
            _user_dict(sender), _user_dict(recipient), amount
        )
    except db.TransferError as e:
        await message.reply(f"❌ {e}")
        return
    except Exception:  # noqa: BLE001
        log.exception("Ошибка перевода")
        await message.reply("⚠️ Что-то пошло не так при переводе. Попробуйте позже.")
        return

    # Картинка: сумма показывается ровно как ввёл пользователь (с запятой)
    amount_display = raw_amount if "," in raw_amount else raw_amount.replace(".", ",")
    recipient_name = _display_name(recipient)

    try:
        png = render_transfer_image(amount_display, recipient_name)
    except Exception:  # noqa: BLE001
        log.exception("Ошибка генерации картинки")
        png = None

    caption = (
        f"#SCAM отправил(а) <b>{amount_display}</b> SCAM для {recipient_name}\n"
        f"💼 Ваш баланс: {_fmt(sender_bal)} SCAM"
    )

    if png:
        await message.reply_photo(
            BufferedInputFile(png, filename="scam.png"),
            caption=caption,
        )
    else:
        await message.reply(caption)


def _fmt(value: Decimal) -> str:
    """Красивый вывод числа: убираем лишние нули, запятая как разделитель."""
    s = format(value.normalize(), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",")


async def main() -> None:
    await db.init_db()
    log.info("База готова. Запускаю polling…")
    # На всякий случай убираем вебхук, если был
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
