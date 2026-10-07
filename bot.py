import asyncio
from datetime import datetime, timezone

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
    init_db,
    get_user,
    create_user,
    set_tariff,
    add_days,
    set_blocked,
    list_users,
    create_promo,
    use_promo,
    list_promos,
)

from github_api import (
    publish_subscription,
)


bot = Bot(BOT_TOKEN)
dp = Dispatcher()

admin_state = {}


def main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🍑 Моя подписка",
                    callback_data="subscription"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎟 Промокод",
                    callback_data="promo"
                )
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Помощь",
                    callback_data="help"
                )
            ],
        ]
    )


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
                    callback_data="admin_tariff"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏳ Добавить дни",
                    callback_data="admin_days"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Заблокировать",
                    callback_data="admin_block"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔓 Разблокировать",
                    callback_data="admin_unblock"
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
                    callback_data="tariff_free"
                ),
                InlineKeyboardButton(
                    text="2️⃣ PRO",
                    callback_data="tariff_pro"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="admin_back"
                )
            ],
        ]
    )


def fmt_date(value):
    try:
        dt = datetime.fromisoformat(
            str(value)
        )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone().strftime(
            "%d.%m.%Y %H:%M:%S"
        )

    except Exception:
        return str(value)


def get_timestamp(value):
    dt = datetime.fromisoformat(
        str(value)
    )

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return int(
        dt.timestamp()
    )


async def rebuild_subscription(
    user
):
    expires_at = get_timestamp(
        user["expires_at"]
    )

    url = publish_subscription(
        user["token"],
        user["tariff"],
        expires_at
    )

    from database import save_subscription_url

    save_subscription_url(
        user["telegram_id"],
        url
    )

    return url


@dp.message(Command("start"))
async def start(message: Message):
    user = create_user(
        message.from_user.id,
        message.from_user.username
    )

    if user["blocked"]:
        await message.answer(
            "🚫 Вы заблокированы."
        )
        return

    try:
        url = await rebuild_subscription(
            user
        )
    except Exception:
        url = user["subscription_url"]

    user = get_user(
        message.from_user.id
    )

    await message.answer(
        "🍑 ПЕРСИК VPN\n\n"
        "🟢 Тариф: "
        + user["tariff"]
        + "\n"
        "📅 До: "
        + fmt_date(user["expires_at"])
        + "\n"
        "📦 Трафик: Безлимит\n\n"
        "🔗 Ссылка:\n"
        + (url or "Ошибка создания ссылки."),
        reply_markup=main_keyboard()
    )


@dp.callback_query(
    F.data == "subscription"
)
async def subscription(
    call: CallbackQuery
):
    user = get_user(
        call.from_user.id
    )

    if not user:
        user = create_user(
            call.from_user.id,
            call.from_user.username
        )

    if user["blocked"]:
        await call.answer(
            "Вы заблокированы.",
            show_alert=True
        )
        return

    await call.message.answer(
        "🍑 МОЯ ПОДПИСКА\n\n"
        "🟢 Тариф: "
        + user["tariff"]
        + "\n"
        "📅 До: "
        + fmt_date(user["expires_at"])
        + "\n"
        "📦 Трафик: Безлимит\n\n"
        "🔗 Ссылка:\n"
        + (
            user["subscription_url"]
            or "Ссылка отсутствует."
        )
    )

    await call.answer()


@dp.callback_query(
    F.data == "promo"
)
async def promo_button(
    call: CallbackQuery
):
    await call.message.answer(
        "🎟 Отправь промокод обычным сообщением."
    )

    await call.answer()


@dp.message(
    lambda message:
    message.from_user.id != ADMIN_ID
    and message.text
    and not message.text.startswith("/")
)
async def promo_message(
    message: Message
):
    user = get_user(
        message.from_user.id
    )

    if not user:
        user = create_user(
            message.from_user.id,
            message.from_user.username
        )

    if user["blocked"]:
        return

    code = message.text.strip()

    result, status = use_promo(
        message.from_user.id,
        code
    )

    if status == "not_found":
        await message.answer(
            "❌ Промокод не найден."
        )
        return

    if status == "disabled":
        await message.answer(
            "❌ Промокод отключён."
        )
        return

    if status == "limit":
        await message.answer(
            "❌ Лимит активаций промокода исчерпан."
        )
        return

    if status == "already_used":
        await message.answer(
            "❌ Ты уже использовал этот промокод."
        )
        return

    try:
        url = await rebuild_subscription(
            result
        )
    except Exception:
        url = result["subscription_url"]

    await message.answer(
        "✅ ПРОМОКОД АКТИВИРОВАН\n\n"
        "🍑 Тариф: "
        + result["tariff"]
        + "\n"
        "📅 До: "
        + fmt_date(result["expires_at"])
        + "\n"
        "🔗 Ссылка:\n"
        + (url or "Ошибка ссылки.")
    )


@dp.callback_query(
    F.data == "help"
)
async def help_callback(
    call: CallbackQuery
):
    await call.message.answer(
        "ℹ️ Помощь\n\n"
        "🍑 Моя подписка — текущий тариф и ссылка.\n"
        "🎟 Промокод — активация промокода."
    )

    await call.answer()


@dp.message(Command("admin"))
async def admin(
    message: Message
):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        "⚙️ АДМИН-ПАНЕЛЬ",
        reply_markup=admin_keyboard()
    )


@dp.callback_query(
    F.data == "admin_back"
)
async def admin_back(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    await call.message.answer(
        "⚙️ АДМИН-ПАНЕЛЬ",
        reply_markup=admin_keyboard()
    )

    await call.answer()


@dp.callback_query(
    F.data == "admin_users"
)
async def admin_users(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    users = list_users()

    if not users:
        text = "👥 Пользователей нет."
    else:
        rows = []

        for user in users:
            username = (
                "@"
                + user["username"]
                if user["username"]
                else "без username"
            )

            status = (
                "🚫"
                if user["blocked"]
                else "🟢"
            )

            rows.append(
                status
                + " "
                + str(user["telegram_id"])
                + " | "
                + username
                + " | "
                + user["tariff"]
                + " | до "
                + fmt_date(
                    user["expires_at"]
                )
            )

        text = (
            "👥 ПОЛЬЗОВАТЕЛИ\n\n"
            + "\n".join(rows)
        )

    await call.message.answer(
        text,
        reply_markup=admin_keyboard()
    )

    await call.answer()


@dp.callback_query(
    F.data == "admin_tariff"
)
async def admin_tariff(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    admin_state[
        ADMIN_ID
    ] = {
        "action": "tariff"
    }

    await call.message.answer(
        "➕ ВЫДАТЬ ТАРИФ\n\n"
        "Выбери тариф:",
        reply_markup=tariff_keyboard()
    )

    await call.answer()


@dp.callback_query(
    F.data == "tariff_free"
)
async def tariff_free(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    admin_state[
        ADMIN_ID
    ] = {
        "action": "tariff",
        "tariff": "Free"
    }

    await call.message.answer(
        "1️⃣ Выбран FREE.\n\n"
        "Теперь отправь Telegram ID пользователя."
    )

    await call.answer()


@dp.callback_query(
    F.data == "tariff_pro"
)
async def tariff_pro(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    admin_state[
        ADMIN_ID
    ] = {
        "action": "tariff",
        "tariff": "PRO"
    }

    await call.message.answer(
        "2️⃣ Выбран PRO.\n\n"
        "Теперь отправь Telegram ID пользователя."
    )

    await call.answer()


@dp.callback_query(
    F.data == "admin_days"
)
async def admin_days(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    admin_state[
        ADMIN_ID
    ] = {
        "action": "days"
    }

    await call.message.answer(
        "⏳ ДОБАВИТЬ ДНИ\n\n"
        "Сначала отправь Telegram ID пользователя."
    )

    await call.answer()


@dp.callback_query(
    F.data == "admin_block"
)
async def admin_block(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    admin_state[
        ADMIN_ID
    ] = {
        "action": "block"
    }

    await call.message.answer(
        "🚫 Отправь Telegram ID пользователя."
    )

    await call.answer()


@dp.callback_query(
    F.data == "admin_unblock"
)
async def admin_unblock(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    admin_state[
        ADMIN_ID
    ] = {
        "action": "unblock"
    }

    await call.message.answer(
        "🔓 Отправь Telegram ID пользователя."
    )

    await call.answer()


@dp.callback_query(
    F.data == "admin_promos"
)
async def admin_promos(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    promos = list_promos()

    if not promos:
        text = "🎟 Промокодов пока нет."
    else:
        rows = []

        for promo in promos:
            status = (
                "🟢"
                if promo["active"]
                else "🔴"
            )

            rows.append(
                status
                + " "
                + promo["code"]
                + " | "
                + promo["tariff"]
                + " | "
                + str(promo["days"])
                + " дн. | "
                + str(promo["uses"])
                + "/"
                + str(promo["max_uses"])
            )

        text = (
            "🎟 ПРОМОКОДЫ\n\n"
            + "\n".join(rows)
            + "\n\n"
            "Для создания:\n"
            "/createpromo КОД ТАРИФ ДНИ ЛИМИТ\n\n"
            "Пример:\n"
            "/createpromo PEACHPRO PRO 30 100"
        )

    await call.message.answer(
        text,
        reply_markup=admin_keyboard()
    )

    await call.answer()


@dp.message(
    Command("createpromo")
)
async def createpromo(
    message: Message
):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()

    if len(parts) != 5:
        await message.answer(
            "❌ Формат:\n"
            "/createpromo КОД ТАРИФ ДНИ ЛИМИТ\n\n"
            "Пример:\n"
            "/createpromo PEACHPRO PRO 30 100"
        )
        return

    code = parts[1].upper()
    tariff = parts[2].upper()

    try:
        days = int(parts[3])
        max_uses = int(parts[4])
    except ValueError:
        await message.answer(
            "❌ Дни и лимит должны быть числами."
        )
        return

    if tariff == "FREE":
        tariff = "Free"
    elif tariff == "PRO":
        tariff = "PRO"
    else:
        await message.answer(
            "❌ Тариф только FREE или PRO."
        )
        return

    if days <= 0 or max_uses <= 0:
        await message.answer(
            "❌ Дни и лимит должны быть больше нуля."
        )
        return

    promo = create_promo(
        code,
        tariff,
        days,
        max_uses
    )

    if not promo:
        await message.answer(
            "❌ Такой промокод уже существует."
        )
        return

    await message.answer(
        "✅ ПРОМОКОД СОЗДАН\n\n"
        "🎟 Код: "
        + code
        + "\n"
        "🍑 Тариф: "
        + tariff
        + "\n"
        "📅 Дней: "
        + str(days)
        + "\n"
        "👥 Активаций: "
        + str(max_uses)
    )


@dp.message(
    F.text
)
async def admin_input(
    message: Message
):
    if message.from_user.id != ADMIN_ID:
        return

    state = admin_state.get(
        ADMIN_ID
    )

    if not state:
        return

    text = message.text.strip()

    if state["action"] == "tariff":
        tariff = state.get(
            "tariff"
        )

        if not tariff:
            return

        try:
            telegram_id = int(text)
        except ValueError:
            await message.answer(
                "❌ Telegram ID должен быть числом."
            )
            return

        user = get_user(
            telegram_id
        )

        if not user:
            user = create_user(
                telegram_id
            )

        old_expire = user[
            "expires_at"
        ]

        user = set_tariff(
            telegram_id,
            tariff
        )

        # ВАЖНО:
        # expires_at здесь вообще не изменяется.
        # Сохраняются дни, часы, минуты и секунды.

        try:
            url = await rebuild_subscription(
                user
            )
        except Exception as error:
            await message.answer(
                "⚠️ Тариф изменён, "
                "но GitHub не обновился:\n"
                + str(error)
            )

            admin_state.pop(
                ADMIN_ID,
                None
            )
            return

        admin_state.pop(
            ADMIN_ID,
            None
        )

        await message.answer(
            "✅ ТАРИФ ВЫДАН\n\n"
            "👤 ID: "
            + str(telegram_id)
            + "\n"
            "🍑 Тариф: "
            + tariff
            + "\n"
            "📅 До: "
            + fmt_date(old_expire)
            + "\n\n"
            "⏱ Срок полностью сохранён "
            "до секунды.",
            reply_markup=admin_keyboard()
        )

        return

    if state["action"] == "days":
        try:
            telegram_id = int(text)
        except ValueError:
            await message.answer(
                "❌ Telegram ID должен быть числом."
            )
            return

        user = get_user(
            telegram_id
        )

        if not user:
            await message.answer(
                "❌ Пользователь не найден."
            )
            return

        admin_state[
            ADMIN_ID
        ] = {
            "action": "days_value",
            "telegram_id": telegram_id
        }

        await message.answer(
            "⏳ Пользователь найден.\n\n"
            "Текущий срок:\n"
            + fmt_date(
                user["expires_at"]
            )
            + "\n\n"
            "Сколько дней добавить?"
        )

        return

    if state["action"] == "days_value":
        try:
            days = int(text)
        except ValueError:
            await message.answer(
                "❌ Введи количество дней числом."
            )
            return

        if days <= 0:
            await message.answer(
                "❌ Количество дней должно быть больше нуля."
            )
            return

        telegram_id = state[
            "telegram_id"
        ]

        user = add_days(
            telegram_id,
            days
        )

        admin_state.pop(
            ADMIN_ID,
            None
        )

        try:
            url = await rebuild_subscription(
                user
            )
        except Exception:
            url = user[
                "subscription_url"
            ]

        await message.answer(
            "✅ ДНИ ДОБАВЛЕНЫ\n\n"
            "👤 ID: "
            + str(telegram_id)
            + "\n"
            "➕ Добавлено: "
            + str(days)
            + " дн.\n"
            "📅 Новый срок: "
            + fmt_date(
                user["expires_at"]
            ),
            reply_markup=admin_keyboard()
        )

        return

    if state["action"] in (
        "block",
        "unblock"
    ):
        try:
            telegram_id = int(text)
        except ValueError:
            await message.answer(
                "❌ Telegram ID должен быть числом."
            )
            return

        user = get_user(
            telegram_id
        )

        if not user:
            await message.answer(
                "❌ Пользователь не найден."
            )
            return

        blocked = (
            state["action"] == "block"
        )

        set_blocked(
            telegram_id,
            blocked
        )

        admin_state.pop(
            ADMIN_ID,
            None
        )

        await message.answer(
            (
                "🚫 Пользователь заблокирован."
                if blocked
                else "🔓 Пользователь разблокирован."
            ),
            reply_markup=admin_keyboard()
        )


async def main():
    init_db()

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":
    asyncio.run(main())
