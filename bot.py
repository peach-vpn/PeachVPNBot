import asyncio
import math
import os
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart

from config import (
    BOT_TOKEN,
    ADMIN_ID,
)

from database import (
    init_db,
    get_user,
    create_user,
    save_subscription_url,
    refresh_user,
    list_users,
    add_days,
    set_blocked,
    delete_user,
    create_promo,
    list_promos,
    use_promo,
)

from github_api import (
    put_file,
    raw_subscription_url,
    subscription_path,
)


bot = Bot(
    token=BOT_TOKEN
)

dp = Dispatcher()

admin_states = {}


PROFILE_TITLE = "🍑 Персик VPN"

ANNOUNCE = (
    "🆓 Бесплатный VPN | "
    "🇳🇱 Нидерланды • "
    "🇩🇪 Германия • "
    "🇰🇿 Казахстан"
)

UPDATE_INTERVAL = 1

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

NODES_FILE = os.path.join(
    BASE_DIR,
    "nodes.txt"
)


def load_nodes():
    if not os.path.exists(
        NODES_FILE
    ):
        return ""

    with open(
        NODES_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        lines = file.readlines()

    result = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        result.append(line)

    return "\n".join(result)


def parse_datetime(value):
    try:
        dt = datetime.fromisoformat(
            value
        )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt

    except Exception:
        return None


def unix_expire(expires_at):
    dt = parse_datetime(
        expires_at
    )

    if not dt:
        return 0

    return int(
        dt.timestamp()
    )


def format_date(
    expires_at
):
    dt = parse_datetime(
        expires_at
    )

    if not dt:
        return "Н/Д"

    return dt.strftime(
        "%d.%m.%Y"
    )


def format_datetime_utc(
    expires_at
):
    dt = parse_datetime(
        expires_at
    )

    if not dt:
        return "Н/Д"

    return dt.strftime(
        "%d.%m.%Y %H:%M UTC"
    )


def remaining_days(
    expires_at
):
    dt = parse_datetime(
        expires_at
    )

    if not dt:
        return 0

    now = datetime.now(
        timezone.utc
    )

    seconds = (
        dt - now
    ).total_seconds()

    if seconds <= 0:
        return 0

    return max(
        1,
        math.ceil(
            seconds / 86400
        )
    )


def subscription_content(
    user,
    nodes=None,
    expired=False
):
    if nodes is None:
        nodes = load_nodes()

    if expired:
        expire = int(
            datetime.now(
                timezone.utc
            ).timestamp()
        )
    else:
        expire = unix_expire(
            user["expires_at"]
        )

    content = (
        "#profile-title: "
        + PROFILE_TITLE
        + "\n"
        "#announce: "
        + ANNOUNCE
        + "\n"
        "#subscription-userinfo: "
        "upload=0; "
        "download=0; "
        "total=0; "
        "expire="
        + str(expire)
        + "\n"
        "#profile-update-interval: "
        + str(UPDATE_INTERVAL)
        + "\n\n"
    )

    if nodes and not expired:
        content += nodes
        content += "\n"

    return content


def make_subscription(
    user
):
    nodes = load_nodes()

    if not nodes:
        raise RuntimeError(
            "nodes.txt пуст или не найден"
        )

    content = subscription_content(
        user,
        nodes=nodes,
        expired=False
    )

    path = subscription_path(
        user["token"]
    )

    put_file(
        path,
        content,
        "Update PeachVPN subscription"
    )

    return raw_subscription_url(
        user["token"]
    )


def invalidate_subscription(
    user
):
    content = subscription_content(
        user,
        nodes="",
        expired=True
    )

    path = subscription_path(
        user["token"]
    )

    put_file(
        path,
        content,
        "Expire PeachVPN subscription"
    )


def main_keyboard(
    user_id
):
    rows = [
        [
            types.InlineKeyboardButton(
                text="📦 Моя подписка",
                callback_data="subscription"
            )
        ],
        [
            types.InlineKeyboardButton(
                text="🎟 Промокод",
                callback_data="promo"
            )
        ],
        [
            types.InlineKeyboardButton(
                text="🔄 Обновить подписку",
                callback_data="refresh_subscription"
            )
        ],
        [
            types.InlineKeyboardButton(
                text="❓ Помощь",
                callback_data="help"
            )
        ],
    ]

    if user_id == ADMIN_ID:
        rows.append(
            [
                types.InlineKeyboardButton(
                    text="🔐 Админ-панель",
                    callback_data="admin"
                )
            ]
        )

    return types.InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def subscription_keyboard():
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="🔄 Обновить подписку",
                    callback_data="refresh_subscription"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="🗑 Удалить подписку",
                    callback_data="delete_subscription"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="⬅️ Главное меню",
                    callback_data="back"
                )
            ],
        ]
    )


def admin_keyboard():
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="👥 Пользователи",
                    callback_data="admin_users"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="🎟 Создать промокод",
                    callback_data="admin_promo_create"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="📋 Промокоды",
                    callback_data="admin_promos"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="➕ Выдать дни",
                    callback_data="admin_days"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="🗑 Удалить подписку",
                    callback_data="admin_delete"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="🚫 Заблокировать",
                    callback_data="admin_block"
                ),
                types.InlineKeyboardButton(
                    text="✅ Разблокировать",
                    callback_data="admin_unblock"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="⬅️ Главное меню",
                    callback_data="back"
                )
            ],
        ]
    )


async def send_main_menu(
    message,
    user
):
    user = refresh_user(
        user["telegram_id"]
    )

    if not user:
        await message.answer(
            "Сначала нажми /start."
        )
        return

    if user["blocked"]:
        await message.answer(
            "🚫 Ты заблокирован."
        )
        return

    status = (
        "🟢"
        if user["active"]
        else "🔴"
    )

    text = (
        "🍑 ПЕРСИК VPN\n\n"
        + status
        + " Подписка: Free\n"
        "📅 До: "
        + format_date(
            user["expires_at"]
        )
        + "\n"
        "📦 Трафик: Безлимит\n\n"
        "🔄 Серверы обновляются автоматически\n\n"
        "👇 Выбери действие:"
    )

    await message.answer(
        text,
        reply_markup=main_keyboard(
            user["telegram_id"]
        )
    )


@dp.message(CommandStart())
async def start(
    message: types.Message
):
    telegram_id = (
        message.from_user.id
    )

    user = get_user(
        telegram_id
    )

    if not user:
        user = create_user(
            telegram_id,
            message.from_user.username or ""
        )

    user = refresh_user(
        telegram_id
    )

    if user["blocked"]:
        await message.answer(
            "🚫 Ты заблокирован."
        )
        return

    if not user["subscription_url"]:
        try:
            url = await asyncio.to_thread(
                make_subscription,
                user
            )

            save_subscription_url(
                telegram_id,
                url
            )

            user = get_user(
                telegram_id
            )

        except Exception as error:
            await message.answer(
                "❌ Не удалось создать подписку.\n\n"
                "Ошибка: "
                + str(error)
            )
            return

    await send_main_menu(
        message,
        user
    )


@dp.callback_query(
    F.data == "back"
)
async def back(
    callback: types.CallbackQuery
):
    await callback.answer()

    admin_states.pop(
        callback.from_user.id,
        None
    )

    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.message.answer(
            "Сначала нажми /start."
        )
        return

    await send_main_menu(
        callback.message,
        user
    )


@dp.callback_query(
    F.data == "subscription"
)
async def subscription(
    callback: types.CallbackQuery
):
    await callback.answer()

    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.message.answer(
            "Сначала нажми /start."
        )
        return

    if user["blocked"]:
        await callback.message.answer(
            "🚫 Ты заблокирован."
        )
        return

    user = refresh_user(
        callback.from_user.id
    )

    status = (
        "Активна"
        if user["active"]
        else "Истекла"
    )

    status_icon = (
        "🟢"
        if user["active"]
        else "🔴"
    )

    text = (
        "🍑 МОЯ ПОДПИСКА\n\n"
        + status_icon
        + " Статус: "
        + status
        + "\n\n"
        "🆓 Тариф: Free\n"
        "📦 Трафик: Безлимит\n"
        "⏳ Осталось дней: "
        + str(
            remaining_days(
                user["expires_at"]
            )
        )
        + "\n"
        "📅 До: "
        + format_datetime_utc(
            user["expires_at"]
        )
        + "\n\n"
        "🔗 Ссылка подписки:\n"
        + (
            user["subscription_url"]
            or "Подписка отсутствует"
        )
    )

    await callback.message.answer(
        text,
        reply_markup=subscription_keyboard()
    )


@dp.callback_query(
    F.data == "refresh_subscription"
)
async def refresh_subscription(
    callback: types.CallbackQuery
):
    await callback.answer(
        "Обновляю..."
    )

    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.message.answer(
            "Сначала нажми /start."
        )
        return

    if user["blocked"]:
        await callback.message.answer(
            "🚫 Ты заблокирован."
        )
        return

    try:
        user = refresh_user(
            callback.from_user.id
        )

        url = await asyncio.to_thread(
            make_subscription,
            user
        )

        save_subscription_url(
            callback.from_user.id,
            url
        )

        user = get_user(
            callback.from_user.id
        )

        await callback.message.answer(
            "✅ Подписка обновлена!\n\n"
            "📅 До: "
            + format_datetime_utc(
                user["expires_at"]
            )
            + "\n\n"
            "🔗 "
            + user["subscription_url"],
            reply_markup=subscription_keyboard()
        )

    except Exception as error:
        await callback.message.answer(
            "❌ Ошибка обновления:\n"
            + str(error)
        )


@dp.callback_query(
    F.data == "delete_subscription"
)
async def delete_subscription_confirm(
    callback: types.CallbackQuery
):
    await callback.answer()

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="❌ Да, удалить",
                    callback_data="delete_subscription_yes"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="⬅️ Отмена",
                    callback_data="subscription"
                )
            ]
        ]
    )

    await callback.message.answer(
        "⚠️ Удалить подписку?\n\n"
        "При обновлении Happ она станет "
        "недействительной.",
        reply_markup=keyboard
    )


@dp.callback_query(
    F.data == "delete_subscription_yes"
)
async def delete_subscription_yes(
    callback: types.CallbackQuery
):
    await callback.answer()

    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.message.answer(
            "Подписка уже удалена."
        )
        return

    try:
        await asyncio.to_thread(
            invalidate_subscription,
            user
        )
    except Exception:
        pass

    delete_user(
        callback.from_user.id
    )

    await callback.message.answer(
        "🗑 Подписка удалена.\n\n"
        "В Happ после обновления она "
        "станет недействительной.\n\n"
        "Если профиль всё ещё виден в Happ, "
        "его нужно удалить в самом Happ.",
        reply_markup=main_keyboard(
            callback.from_user.id
        )
    )


@dp.callback_query(
    F.data == "promo"
)
async def promo_start(
    callback: types.CallbackQuery
):
    await callback.answer()

    admin_states[
        callback.from_user.id
    ] = "promo"

    await callback.message.answer(
        "🎟 Введи промокод:"
    )


@dp.callback_query(
    F.data == "help"
)
async def help_menu(
    callback: types.CallbackQuery
):
    await callback.answer()

    await callback.message.answer(
        "❓ ПОМОЩЬ\n\n"
        "1️⃣ Открой «Моя подписка».\n"
        "2️⃣ Скопируй ссылку подписки.\n"
        "3️⃣ Добавь её в Happ.\n\n"
        "🔄 Серверы обновляются автоматически.\n\n"
        "🎟 Есть промокод?\n"
        "Открой раздел «Промокод»."
    )


@dp.callback_query(
    F.data == "admin"
)
async def admin_panel(
    callback: types.CallbackQuery
):
    await callback.answer()

    if callback.from_user.id != ADMIN_ID:
        return

    admin_states.pop(
        callback.from_user.id,
        None
    )

    await callback.message.answer(
        "🔐 АДМИН-ПАНЕЛЬ\n\n"
        "Выбери действие:",
        reply_markup=admin_keyboard()
    )


@dp.message(
    F.text == "/admin"
)
async def admin_command(
    message: types.Message
):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        "🔐 АДМИН-ПАНЕЛЬ\n\n"
        "Выбери действие:",
        reply_markup=admin_keyboard()
    )


@dp.callback_query(
    F.data == "admin_users"
)
async def admin_users(
    callback: types.CallbackQuery
):
    await callback.answer()

    if callback.from_user.id != ADMIN_ID:
        return

    users = list_users()

    if not users:
        await callback.message.answer(
            "👥 Пользователей нет."
        )
        return

    text = "👥 ПОЛЬЗОВАТЕЛИ\n\n"

    for user in users:
        username = (
            user["username"]
            or "без username"
        )

        status = (
            "🚫 Заблокирован"
            if user["blocked"]
            else (
                "🟢 Активна"
                if user["active"]
                else "🔴 Истекла"
            )
        )

        text += (
            "🆔 "
            + str(user["telegram_id"])
            + "\n"
            "@"
            + username.lstrip("@")
            + "\n"
            + status
            + "\n"
            "📅 До: "
            + format_datetime_utc(
                user["expires_at"]
            )
            + "\n\n"
        )

    await callback.message.answer(
        text
    )


@dp.callback_query(
    F.data == "admin_promo_create"
)
async def admin_promo_create(
    callback: types.CallbackQuery
):
    await callback.answer()

    if callback.from_user.id != ADMIN_ID:
        return

    admin_states[
        callback.from_user.id
    ] = "admin_promo"

    await callback.message.answer(
        "🎟 СОЗДАНИЕ ПРОМОКОДА\n\n"
        "Отправь:\n"
        "КОД ДНИ ЛИМИТ\n\n"
        "Пример:\n"
        "FREE7 7 100"
    )


@dp.callback_query(
    F.data == "admin_promos"
)
async def admin_promos(
    callback: types.CallbackQuery
):
    await callback.answer()

    if callback.from_user.id != ADMIN_ID:
        return

    promos = list_promos()

    if not promos:
        await callback.message.answer(
            "🎟 Промокодов нет."
        )
        return

    text = "🎟 ПРОМОКОДЫ\n\n"

    for promo in promos:
        text += (
            "🔑 "
            + promo["code"]
            + "\n"
            "📅 Дней: "
            + str(promo["days"])
            + "\n"
            "👥 Использований: "
            + str(promo["uses"])
            + "/"
            + str(promo["max_uses"])
            + "\n\n"
        )

    await callback.message.answer(
        text
    )


@dp.callback_query(
    F.data == "admin_days"
)
async def admin_days(
    callback: types.CallbackQuery
):
    await callback.answer()

    if callback.from_user.id != ADMIN_ID:
        return

    admin_states[
        callback.from_user.id
    ] = "admin_days"

    await callback.message.answer(
        "➕ ВЫДАТЬ ДНИ\n\n"
        "Отправь:\n"
        "ID ДНИ\n\n"
        "Пример:\n"
        "123456789 30"
    )


@dp.callback_query(
    F.data == "admin_delete"
)
async def admin_delete(
    callback: types.CallbackQuery
):
    await callback.answer()

    if callback.from_user.id != ADMIN_ID:
        return

    admin_states[
        callback.from_user.id
    ] = "admin_delete"

    await callback.message.answer(
        "🗑 УДАЛИТЬ ПОДПИСКУ\n\n"
        "Отправь Telegram ID."
    )


@dp.callback_query(
    F.data == "admin_block"
)
async def admin_block(
    callback: types.CallbackQuery
):
    await callback.answer()

    if callback.from_user.id != ADMIN_ID:
        return

    admin_states[
        callback.from_user.id
    ] = "admin_block"

    await callback.message.answer(
        "🚫 БЛОКИРОВКА\n\n"
        "Отправь Telegram ID."
    )


@dp.callback_query(
    F.data == "admin_unblock"
)
async def admin_unblock(
    callback: types.CallbackQuery
):
    await callback.answer()

    if callback.from_user.id != ADMIN_ID:
        return

    admin_states[
        callback.from_user.id
    ] = "admin_unblock"

    await callback.message.answer(
        "✅ РАЗБЛОКИРОВКА\n\n"
        "Отправь Telegram ID."
    )


@dp.message(F.text)
async def text_handler(
    message: types.Message
):
    user_id = message.from_user.id
    text = message.text.strip()

    state = admin_states.get(
        user_id
    )

    if user_id == ADMIN_ID:

        if state == "admin_promo":
            parts = text.split()

            if len(parts) != 3:
                await message.answer(
                    "❌ Формат:\n"
                    "КОД ДНИ ЛИМИТ"
                )
                return

            code = parts[0]

            try:
                days = int(
                    parts[1]
                )

                max_uses = int(
                    parts[2]
                )

                if days <= 0:
                    raise ValueError

                if max_uses <= 0:
                    raise ValueError

            except ValueError:
                await message.answer(
                    "❌ Дни и лимит должны "
                    "быть положительными числами."
                )
                return

            try:
                create_promo(
                    code,
                    days,
                    max_uses
                )

                admin_states.pop(
                    user_id,
                    None
                )

                await message.answer(
                    "✅ ПРОМОКОД СОЗДАН\n\n"
                    "🎟 Код: "
                    + code.upper()
                    + "\n"
                    "📅 Дней: "
                    + str(days)
                    + "\n"
                    "👥 Лимит: "
                    + str(max_uses),
                    reply_markup=admin_keyboard()
                )

            except Exception as error:
                await message.answer(
                    "❌ Ошибка:\n"
                    + str(error)
                )

            return

        if state == "admin_days":
            parts = text.split()

            if len(parts) != 2:
                await message.answer(
                    "❌ Формат:\n"
                    "ID ДНИ"
                )
                return

            try:
                target_id = int(
                    parts[0]
                )

                days = int(
                    parts[1]
                )

                if days <= 0:
                    raise ValueError

            except ValueError:
                await message.answer(
                    "❌ Формат:\n"
                    "ID ДНИ"
                )
                return

            user = add_days(
                target_id,
                days
            )

            admin_states.pop(
                user_id,
                None
            )

            if not user:
                await message.answer(
                    "❌ Пользователь не найден.",
                    reply_markup=admin_keyboard()
                )
                return

            try:
                url = await asyncio.to_thread(
                    make_subscription,
                    user
                )

                save_subscription_url(
                    target_id,
                    url
                )

            except Exception as error:
                await message.answer(
                    "⚠️ Дни выданы, "
                    "но GitHub не обновился:\n"
                    + str(error),
                    reply_markup=admin_keyboard()
                )
                return

            await message.answer(
                "✅ Дни выданы\n\n"
                "🆔 ID: "
                + str(target_id)
                + "\n"
                "➕ Дней: "
                + str(days)
                + "\n"
                "📅 До: "
                + format_datetime_utc(
                    user["expires_at"]
                ),
                reply_markup=admin_keyboard()
            )

            return

        if state == "admin_delete":
            try:
                target_id = int(
                    text
                )

            except ValueError:
                await message.answer(
                    "❌ ID должен быть числом."
                )
                return

            user = get_user(
                target_id
            )

            admin_states.pop(
                user_id,
                None
            )

            if not user:
                await message.answer(
                    "❌ Пользователь не найден.",
                    reply_markup=admin_keyboard()
                )
                return

            try:
                await asyncio.to_thread(
                    invalidate_subscription,
                    user
                )
            except Exception:
                pass

            delete_user(
                target_id
            )

            await message.answer(
                "🗑 Подписка удалена.\n\n"
                "🆔 ID: "
                + str(target_id),
                reply_markup=admin_keyboard()
            )

            return

        if state in (
            "admin_block",
            "admin_unblock"
        ):
            try:
                target_id = int(
                    text
                )

            except ValueError:
                await message.answer(
                    "❌ ID должен быть числом."
                )
                return

            user = get_user(
                target_id
            )

            if not user:
                await message.answer(
                    "❌ Пользователь не найден."
                )
                return

            blocking = (
                state == "admin_block"
            )

            if blocking:
                try:
                    await asyncio.to_thread(
                        invalidate_subscription,
                        user
                    )
                except Exception:
                    pass

            set_blocked(
                target_id,
                blocking
            )

            admin_states.pop(
                user_id,
                None
            )

            await message.answer(
                (
                    "🚫 Пользователь заблокирован."
                    if blocking
                    else
                    "✅ Пользователь разблокирован."
                )
                + "\n\n🆔 ID: "
                + str(target_id),
                reply_markup=admin_keyboard()
            )

            return

    if state == "promo":
        admin_states.pop(
            user_id,
            None
        )

        user = get_user(
            user_id
        )

        if not user:
            user = create_user(
                user_id,
                message.from_user.username or ""
            )

        if user["blocked"]:
            await message.answer(
                "🚫 Ты заблокирован."
            )
            return

        success, result = use_promo(
            text,
            user_id
        )

        if not success:
            await message.answer(
                "❌ "
                + str(result),
                reply_markup=main_keyboard(
                    user_id
                )
            )
            return

        days = int(result)

        updated = add_days(
            user_id,
            days
        )

        try:
            url = await asyncio.to_thread(
                make_subscription,
                updated
            )

            save_subscription_url(
                user_id,
                url
            )

        except Exception as error:
            await message.answer(
                "⚠️ Промокод применён, "
                "но подписку не удалось "
                "обновить:\n"
                + str(error)
            )
            return

        await message.answer(
            "🎉 ПРОМОКОД АКТИВИРОВАН\n\n"
            "➕ Добавлено дней: "
            + str(days)
            + "\n"
            "📅 До: "
            + format_datetime_utc(
                updated["expires_at"]
            ),
            reply_markup=main_keyboard(
                user_id
            )
        )

        return

    user = get_user(
        user_id
    )

    if not user:
        user = create_user(
            user_id,
            message.from_user.username or ""
        )

    await send_main_menu(
        message,
        user
    )


async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не задан"
        )

    init_db()

    print(
        "🍑 Персик VPN Bot запущен"
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":
    asyncio.run(main())
