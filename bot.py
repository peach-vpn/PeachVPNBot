import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import (
    BOT_TOKEN,
    ADMIN_ID,
    FREE_DAYS,
)

from database import (
    create_user,
    get_user,
    set_tariff,
    add_days,
    set_blocked,
    list_users,
    create_promo,
    list_promos,
    use_promo,
)

from github_api import (
    publish_subscription,
)


logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def fmt_date(value):
    if not value:
        return "—"

    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return str(value)


def main_keyboard(user_id: int):
    buttons = [
        [
            InlineKeyboardButton(
                text="🍑 Моя подписка",
                callback_data="my_subscription"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔗 Моя ссылка",
                callback_data="my_link"
            )
        ],
    ]

    if is_admin(user_id):
        buttons.append([
            InlineKeyboardButton(
                text="⚙️ Админ-панель",
                callback_data="admin_panel"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👥 Пользователи",
                    callback_data="admin_users"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎟 Промокоды",
                    callback_data="admin_promos"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Выдать тариф",
                    callback_data="admin_give_tariff"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏳ Добавить дни",
                    callback_data="admin_add_days"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Блокировки",
                    callback_data="admin_blocks"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_main"
                )
            ],
        ]
    )


def tariff_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1️⃣ FREE",
                    callback_data="tariff_FREE"
                ),
                InlineKeyboardButton(
                    text="2️⃣ PRO",
                    callback_data="tariff_PRO"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="admin_panel"
                )
            ],
        ]
    )


# ============================================================
# ОБНОВЛЕНИЕ ПОДПИСКИ
# ============================================================

async def rebuild_subscription(user):
    if not user:
        return None

    token = user["token"]
    tariff = user["tariff"]
    expires_at = user["expires_at"]

    url = publish_subscription(
        token=token,
        tariff=tariff,
        expires_at=expires_at,
    )

    return url


# ============================================================
# START
# ============================================================

@dp.message(Command("start"))
async def start_command(message: Message):
    user = get_user(message.from_user.id)

    if not user:
        user = create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

        try:
            await asyncio.to_thread(
                rebuild_subscription,
                user
            )
        except Exception:
            logging.exception("Ошибка создания подписки")

    elif user.get("blocked"):
        await message.answer(
            "🚫 Вы заблокированы."
        )
        return

    await message.answer(
        "🍑 ПЕРСИК VPN\n\n"
        f"🟢 Подписка: {user['tariff']}\n"
        f"📅 До: {fmt_date(user['expires_at'])}\n"
        "📦 Трафик: Безлимит\n\n"
        "👇 Выбери действие:",
        reply_markup=main_keyboard(message.from_user.id)
    )


# ============================================================
# ADMIN COMMAND
# ============================================================

@dp.message(Command("admin"))
async def admin_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return

    await message.answer(
        "⚙️ АДМИН-ПАНЕЛЬ\n\n"
        "Выбери действие:",
        reply_markup=admin_keyboard()
    )


# ============================================================
# CALLBACKS
# ============================================================

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        "⚙️ АДМИН-ПАНЕЛЬ\n\n"
        "Выбери действие:",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery):
    user = get_user(callback.from_user.id)

    if not user:
        await callback.answer("Сначала нажми /start")
        return

    await callback.message.edit_text(
        "🍑 ПЕРСИК VPN\n\n"
        f"🟢 Подписка: {user['tariff']}\n"
        f"📅 До: {fmt_date(user['expires_at'])}\n"
        "📦 Трафик: Безлимит\n\n"
        "👇 Выбери действие:",
        reply_markup=main_keyboard(callback.from_user.id)
    )

    await callback.answer()


# ============================================================
# МОЯ ПОДПИСКА
# ============================================================

@dp.callback_query(F.data == "my_subscription")
async def my_subscription(callback: CallbackQuery):
    user = get_user(callback.from_user.id)

    if not user:
        await callback.answer(
            "Сначала нажми /start",
            show_alert=True
        )
        return

    if user.get("blocked"):
        await callback.answer(
            "🚫 Вы заблокированы",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        "🍑 МОЯ ПОДПИСКА\n\n"
        f"🟢 Статус: Активна\n"
        f"💎 Тариф: {user['tariff']}\n"
        f"📅 До: {fmt_date(user['expires_at'])}\n\n"
        "🔗 Ссылка:\n\n"
        f"{user['subscription_url']}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Обновить",
                        callback_data="refresh_subscription"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="back_main"
                    )
                ],
            ]
        )
    )

    await callback.answer()


# ============================================================
# МОЯ ССЫЛКА
# ============================================================

@dp.callback_query(F.data == "my_link")
async def my_link(callback: CallbackQuery):
    user = get_user(callback.from_user.id)

    if not user:
        await callback.answer(
            "Сначала нажми /start",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        "🔗 МОЯ ССЫЛКА\n\n"
        f"{user['subscription_url']}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="back_main"
                    )
                ]
            ]
        )
    )

    await callback.answer()


# ============================================================
# ОБНОВИТЬ ПОДПИСКУ
# ============================================================

@dp.callback_query(F.data == "refresh_subscription")
async def refresh_subscription(callback: CallbackQuery):
    user = get_user(callback.from_user.id)

    if not user:
        await callback.answer(
            "Пользователь не найден",
            show_alert=True
        )
        return

    try:
        await asyncio.to_thread(
            rebuild_subscription,
            user
        )

        await callback.answer(
            "✅ Подписка обновлена"
        )

        await my_subscription(callback)

    except Exception:
        logging.exception("Ошибка обновления")

        await callback.answer(
            "❌ Ошибка обновления",
            show_alert=True
        )


# ============================================================
# АДМИН: ПОЛЬЗОВАТЕЛИ
# ============================================================

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    users = list_users()

    if not users:
        text = "👥 ПОЛЬЗОВАТЕЛИ\n\nПользователей пока нет."
    else:
        lines = ["👥 ПОЛЬЗОВАТЕЛИ\n"]

        for user in users[:50]:
            status = "🚫" if user["blocked"] else "🟢"

            lines.append(
                f"{status} ID: {user['telegram_id']}\n"
                f"💎 {user['tariff']}\n"
                f"📅 {fmt_date(user['expires_at'])}\n"
            )

        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="admin_panel"
                    )
                ]
            ]
        )
    )

    await callback.answer()


# ============================================================
# АДМИН: ПРОМОКОДЫ
# ============================================================

@dp.callback_query(F.data == "admin_promos")
async def admin_promos(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    promos = list_promos()

    lines = [
        "🎟 ПРОМОКОДЫ\n"
    ]

    if not promos:
        lines.append("Промокодов пока нет.")
    else:
        for promo in promos:
            tariff = promo["tariff"]

            lines.append(
                f"🎟 {promo['code']}\n"
                f"💎 Тариф: {tariff}\n"
                f"📅 Дней: {promo['days']}\n"
                f"👥 Использований: "
                f"{promo['uses']}/{promo['max_uses']}\n"
                f"🟢 Активен: "
                f"{'Да' if promo['active'] else 'Нет'}\n"
            )

    lines.append(
        "\nСоздать:\n"
        "/createpromo КОД ТАРИФ ДНИ ЛИМИТ\n\n"
        "Пример:\n"
        "/createpromo PEACHPRO PRO 30 100"
    )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="admin_panel"
                    )
                ]
            ]
        )
    )

    await callback.answer()


# ============================================================
# АДМИН: ВЫДАТЬ ТАРИФ
# ============================================================

@dp.callback_query(F.data == "admin_give_tariff")
async def admin_give_tariff(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        "➕ ВЫДАТЬ ТАРИФ\n\n"
        "Выбери тариф:",
        reply_markup=tariff_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("tariff_"))
async def select_tariff(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    tariff = callback.data.replace(
        "tariff_",
        ""
    )

    if tariff not in ("FREE", "PRO"):
        await callback.answer(
            "Неизвестный тариф",
            show_alert=True
        )
        return

    await state_set(
        callback.from_user.id,
        {
            "action": "give_tariff",
            "tariff": tariff,
        }
    )

    await callback.message.edit_text(
        "➕ ВЫДАТЬ ТАРИФ\n\n"
        f"💎 Выбран тариф: {tariff}\n\n"
        "Введите Telegram ID пользователя:"
    )

    await callback.answer()


# ============================================================
# АДМИН: ДОБАВИТЬ ДНИ
# ============================================================

@dp.callback_query(F.data == "admin_add_days")
async def admin_add_days(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    await state_set(
        callback.from_user.id,
        {
            "action": "add_days_id"
        }
    )

    await callback.message.edit_text(
        "⏳ ДОБАВИТЬ ДНИ\n\n"
        "Введите Telegram ID пользователя:"
    )

    await callback.answer()


# ============================================================
# АДМИН: БЛОКИРОВКА
# ============================================================

@dp.callback_query(F.data == "admin_blocks")
async def admin_blocks(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    await state_set(
        callback.from_user.id,
        {
            "action": "block_id"
        }
    )

    await callback.message.edit_text(
        "🚫 БЛОКИРОВКИ\n\n"
        "Введите Telegram ID пользователя:"
    )

    await callback.answer()


# ============================================================
# ПРОМОКОД
# ============================================================

@dp.message(Command("createpromo"))
async def createpromo_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(
            "⛔ Доступ запрещён."
        )
        return

    parts = message.text.split()

    if len(parts) != 5:
        await message.answer(
            "❌ Формат:\n\n"
            "/createpromo КОД ТАРИФ ДНИ ЛИМИТ\n\n"
            "Пример:\n"
            "/createpromo PEACHPRO PRO 30 100"
        )
        return

    _, code, tariff, days, limit = parts

    tariff = tariff.upper()

    if tariff in ("1", "FREE"):
        tariff = "FREE"
    elif tariff in ("2", "PRO"):
        tariff = "PRO"
    else:
        await message.answer(
            "❌ Тариф должен быть 1/FREE или 2/PRO."
        )
        return

    try:
        days = int(days)
        limit = int(limit)

        if days <= 0 or limit <= 0:
            raise ValueError

    except ValueError:
        await message.answer(
            "❌ Дни и лимит должны быть числами больше 0."
        )
        return

    try:
        create_promo(
            code=code.upper(),
            tariff=tariff,
            days=days,
            max_uses=limit,
        )

        await message.answer(
            "✅ ПРОМОКОД СОЗДАН\n\n"
            f"🎟 Код: {code.upper()}\n"
            f"💎 Тариф: {tariff}\n"
            f"📅 Дней: {days}\n"
            f"👥 Лимит: {limit}"
        )

    except Exception as e:
        logging.exception("Ошибка создания промокода")

        await message.answer(
            f"❌ Не удалось создать промокод:\n{e}"
        )


# ============================================================
# СОСТОЯНИЯ АДМИНА
# ============================================================

ADMIN_STATES = {}


async def state_set(user_id, data):
    ADMIN_STATES[user_id] = data


def state_get(user_id):
    return ADMIN_STATES.get(user_id)


def state_clear(user_id):
    ADMIN_STATES.pop(user_id, None)


# ============================================================
# ВВОД АДМИНА
# ============================================================

@dp.message(F.text)
async def admin_text_input(message: Message):
    if not is_admin(message.from_user.id):
        return

    state = state_get(message.from_user.id)

    if not state:
        return

    text = message.text.strip()
    action = state.get("action")

    # --------------------------------------------------------
    # ВЫДАТЬ ТАРИФ
    # --------------------------------------------------------

    if action == "give_tariff":
        try:
            telegram_id = int(text)
        except ValueError:
            await message.answer(
                "❌ Telegram ID должен быть числом."
            )
            return

        user = get_user(telegram_id)

        if not user:
            await message.answer(
                "❌ Пользователь не найден."
            )
            state_clear(message.from_user.id)
            return

        tariff = state["tariff"]

        old_expire = user["expires_at"]

        set_tariff(
            telegram_id,
            tariff
        )

        updated_user = get_user(telegram_id)

        try:
            await asyncio.to_thread(
                rebuild_subscription,
                updated_user
            )
        except Exception:
            logging.exception(
                "Ошибка публикации тарифа"
            )

        state_clear(message.from_user.id)

        await message.answer(
            "✅ ТАРИФ ВЫДАН\n\n"
            f"👤 ID: {telegram_id}\n"
            f"💎 Тариф: {tariff}\n\n"
            f"📅 Срок НЕ изменён:\n"
            f"{fmt_date(old_expire)}\n\n"
            "Ни один день не добавлен.",
            reply_markup=admin_keyboard()
        )

        return

    # --------------------------------------------------------
    # ДОБАВИТЬ ДНИ — ВВОД ID
    # --------------------------------------------------------

    if action == "add_days_id":
        try:
            telegram_id = int(text)
        except ValueError:
            await message.answer(
                "❌ Telegram ID должен быть числом."
            )
            return

        user = get_user(telegram_id)

        if not user:
            await message.answer(
                "❌ Пользователь не найден."
            )
            state_clear(message.from_user.id)
            return

        await state_set(
            message.from_user.id,
            {
                "action": "add_days_value",
                "telegram_id": telegram_id,
            }
        )

        await message.answer(
            "⏳ ДОБАВИТЬ ДНИ\n\n"
            f"👤 ID: {telegram_id}\n"
            f"📅 Сейчас до: {fmt_date(user['expires_at'])}\n\n"
            "Введите количество дней:"
        )

        return

    # --------------------------------------------------------
    # ДОБАВИТЬ ДНИ — ВВОД КОЛИЧЕСТВА
    # --------------------------------------------------------

    if action == "add_days_value":
        try:
            days = int(text)

            if days <= 0:
                raise ValueError

        except ValueError:
            await message.answer(
                "❌ Введите положительное число дней."
            )
            return

        telegram_id = state["telegram_id"]

        user = get_user(telegram_id)

        if not user:
            await message.answer(
                "❌ Пользователь не найден."
            )
            state_clear(message.from_user.id)
            return

        old_expire = user["expires_at"]

        add_days(
            telegram_id,
            days
        )

        updated_user = get_user(telegram_id)

        try:
            await asyncio.to_thread(
                rebuild_subscription,
                updated_user
            )
        except Exception:
            logging.exception(
                "Ошибка публикации"
            )

        state_clear(message.from_user.id)

        await message.answer(
            "✅ ДНИ ДОБАВЛЕНЫ\n\n"
            f"👤 ID: {telegram_id}\n"
            f"➕ Добавлено: {days} дн.\n\n"
            f"📅 Было до:\n"
            f"{fmt_date(old_expire)}\n\n"
            f"📅 Стало до:\n"
            f"{fmt_date(updated_user['expires_at'])}",
            reply_markup=admin_keyboard()
        )

        return

    # --------------------------------------------------------
    # БЛОКИРОВКА
    # --------------------------------------------------------

    if action == "block_id":
        try:
            telegram_id = int(text)
        except ValueError:
            await message.answer(
                "❌ Telegram ID должен быть числом."
            )
            return

        user = get_user(telegram_id)

        if not user:
            await message.answer(
                "❌ Пользователь не найден."
            )
            state_clear(message.from_user.id)
            return

        await state_set(
            message.from_user.id,
            {
                "action": "block_choice",
                "telegram_id": telegram_id,
            }
        )

        await message.answer(
            f"🚫 Пользователь: {telegram_id}\n\n"
            "Выбери действие:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🚫 Заблокировать",
                            callback_data="block_yes"
                        ),
                        InlineKeyboardButton(
                            text="🟢 Разблокировать",
                            callback_data="block_no"
                        ),
                    ]
                ]
            )
        )

        return


# ============================================================
# БЛОК / РАЗБЛОК
# ============================================================

@dp.callback_query(F.data == "block_yes")
async def block_yes(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    state = state_get(callback.from_user.id)

    if not state:
        await callback.answer(
            "Сессия закончилась",
            show_alert=True
        )
        return

    telegram_id = state["telegram_id"]

    set_blocked(
        telegram_id,
        True
    )

    state_clear(callback.from_user.id)

    await callback.message.edit_text(
        f"🚫 Пользователь {telegram_id} заблокирован.",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "block_no")
async def block_no(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    state = state_get(callback.from_user.id)

    if not state:
        await callback.answer(
            "Сессия закончилась",
            show_alert=True
        )
        return

    telegram_id = state["telegram_id"]

    set_blocked(
        telegram_id,
        False
    )

    state_clear(callback.from_user.id)

    await callback.message.edit_text(
        f"🟢 Пользователь {telegram_id} разблокирован.",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


# ============================================================
# ПРОМОКОД ДЛЯ ПОЛЬЗОВАТЕЛЯ
# ============================================================

@dp.message(F.text.startswith("/promo"))
async def promo_command(message: Message):
    user = get_user(message.from_user.id)

    if not user:
        await message.answer(
            "Сначала нажми /start."
        )
        return

    if user.get("blocked"):
        await message.answer(
            "🚫 Вы заблокированы."
        )
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) != 2:
        await message.answer(
            "❌ Использование:\n"
            "/promo КОД"
        )
        return

    code = parts[1].strip().upper()

    try:
        result = use_promo(
            code,
            message.from_user.id
        )

        updated_user = get_user(
            message.from_user.id
        )

        await asyncio.to_thread(
            rebuild_subscription,
            updated_user
        )

        await message.answer(
            "🎉 ПРОМОКОД АКТИВИРОВАН!\n\n"
            f"💎 Тариф: {updated_user['tariff']}\n"
            f"📅 До: {fmt_date(updated_user['expires_at'])}"
        )

    except Exception as e:
        await message.answer(
            f"❌ {e}"
        )


# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не задан"
        )

    logging.info(
        "🍑 PeachVPN Bot запущен"
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
