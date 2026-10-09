import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

SUBSCRIPTION_URL = "https://peach-vpn.github.io/subscribe"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🍑 Получить VPN",
                    callback_data="get_vpn",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📲 Как подключить",
                    callback_data="how_to",
                )
            ],
        ]
    )


def back_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back",
                )
            ]
        ]
    )


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "🍑 ПЕРСИК VPN\n\n"
        "🟢 Бесплатный VPN\n"
        "🌍 Полная подписка с серверами\n"
        "📱 Поддержка Happ\n\n"
        "Нажми кнопку ниже, чтобы получить VPN.",
        reply_markup=main_keyboard(),
    )


@dp.callback_query(F.data == "get_vpn")
async def get_vpn(callback: CallbackQuery):
    await callback.message.edit_text(
        "🍑 ПЕРСИК VPN\n\n"
        "🔗 Твоя ссылка на полную подписку:\n\n"
        f"{SUBSCRIPTION_URL}\n\n"
        "📋 Скопируй ссылку и добавь её в Happ.\n"
        "Список серверов обновляется через подписку.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📲 Как подключить",
                        callback_data="how_to",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="back",
                    )
                ],
            ]
        ),
        disable_web_page_preview=True,
    )
    await callback.answer()


@dp.callback_query(F.data == "how_to")
async def how_to(callback: CallbackQuery):
    await callback.message.edit_text(
        "📲 КАК ПОДКЛЮЧИТЬ 🍑 ПЕРСИК VPN\n\n"
        "1️⃣ Установи Happ.\n\n"
        "2️⃣ Нажми «Получить VPN» в боте.\n\n"
        "3️⃣ Скопируй ссылку на подписку.\n\n"
        "4️⃣ Открой Happ и найди добавление подписки "
        "по URL.\n\n"
        "5️⃣ Вставь ссылку и обнови список серверов.\n\n"
        "6️⃣ Выбери сервер и подключись.\n\n"
        "Если названия кнопок отличаются, они могут "
        "зависеть от версии Happ.",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "back")
async def back(callback: CallbackQuery):
    await callback.message.edit_text(
        "🍑 ПЕРСИК VPN\n\n"
        "🟢 Бесплатный VPN\n"
        "🌍 Полная подписка с серверами\n"
        "📱 Поддержка Happ\n\n"
        "Выбери действие:",
        reply_markup=main_keyboard(),
    )
    await callback.answer()


async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "Не задан BOT_TOKEN в переменных окружения!"
        )

    logging.info("🍑 Персик VPN запущен")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
