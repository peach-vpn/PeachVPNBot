import asyncio
import math
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import BOT_TOKEN, ADMIN_ID

from database import (
    init_db,
    get_user,
    create_user,
    refresh_user,
    list_users,
    add_days,
    set_blocked,
    delete_user,
    create_promo,
    list_promos,
    use_promo,
    save_subscription_url,
)

from github_api import (
    put_file_verified,
    raw_subscription_url,
    subscription_path,
)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

PROFILE_TITLE = "🍑 Персик VPN"

ANNOUNCE = (
    "🆓 Бесплатный VPN | "
    "🇳🇱 Нидерланды • "
    "🇩🇪 Германия • "
    "🇰🇿 Казахстан"
)

NODES_FILE = "nodes.txt"

admin_states = {}


def main_keyboard(is_admin=False):
    buttons = [
        [
            InlineKeyboardButton(
                text="📦 Моя подписка",
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
                text="❓ Помощь",
                callback_data="help"
            )
        ],
    ]

    if is_admin:
        buttons.append([
            InlineKeyboardButton(
                text="🔐 Админ-панель",
                callback_data="admin"
            )
        ])

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


def subscription_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Обновить подписку",
                    callback_data="refresh"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить подписку",
                    callback_data="delete_my_subscription"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="back"
                )
            ],
        ]
    )


def back_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="back"
                )
            ]
        ]
    )


def admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👥 Участники",
                    callback_data="admin_users"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎟 Создать промокод",
                    callback_data="admin_create_promo"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Промокоды",
                    callback_data="admin_promos"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Выдать дни",
                    callback_data="admin_add_days"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить подписку",
                    callback_data="admin_delete"
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
                    text="✅ Разблокировать",
                    callback_data="admin_unblock"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="back"
                )
            ],
        ]
    )


def delete_confirm_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Да, удалить",
                    callback_data="confirm_delete_my_subscription"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="subscription"
                )
            ],
        ]
    )


def load_nodes():
    try:
        with open(
            NODES_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            lines = file.readlines()
    except Exception:
        return []

    result = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if "://" not in line:
            continue

        result.append(line)

    return result


def expire_timestamp(user):
    expires = datetime.fromisoformat(
        user["expires_at"]
    )

    if expires.tzinfo is None:
        expires = expires.replace(
            tzinfo=timezone.utc
        )

    return int(
        expires.timestamp()
    )


def build_subscription(user):
    expire = expire_timestamp(user)

    lines = [
        "#profile-title: " + PROFILE_TITLE,
        "#announce: " + ANNOUNCE,
        (
            "#subscription-userinfo: "
            "upload=0; "
            "download=0; "
            "total=0; "
            "expire="
            + str(expire)
        ),
        "#profile-update-interval: 1",
        "",
    ]

    lines.extend(
        load_nodes()
    )

    lines.append("")

    return "\n".join(lines)


def update_github_subscription(user):
    content = build_subscription(
        user
    )

    path = subscription_path(
        user["token"]
    )

    put_file_verified(
        path,
        content,
        "Update PeachVPN subscription "
        + str(user["telegram_id"])
    )

    url = raw_subscription_url(
        user["token"]
    )

    save_subscription_url(
        user["telegram_id"],
        url
    )

    return url


def invalidate_github_subscription(user):
    content = "\n".join([
        "#profile-title: " + PROFILE_TITLE,
        "#announce: Подписка отключена",
        (
            "#subscription-userinfo: "
            "upload=0; "
            "download=0; "
            "total=0; "
            "expire=1"
        ),
        "#profile-update-interval: 1",
        "",
    ])

    put_file_verified(
        subscription_path(
            user["token"]
        ),
        content,
        "Disable PeachVPN subscription "
        + str(user["telegram_id"])
    )


def main_text(user):
    user = refresh_user(
        user["telegram_id"]
    )

    if not user:
        return "❌ Пользователь не найден."

    if user["blocked"]:
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "🚫 Подписка заблокирована."
        )

    try:
        expires = datetime.fromisoformat(
            user["expires_at"]
        )

        if expires.tzinfo is None:
            expires = expires.replace(
                tzinfo=timezone.utc
            )

        seconds = (
            expires
            - datetime.now(timezone.utc)
        ).total_seconds()

        days = max(
            0,
            math.ceil(
                seconds / 86400
            )
        )

        date_text = expires.strftime(
            "%d.%m.%Y"
        )

    except Exception:
        days = 0
        date_text = "Неизвестно"

    status = (
        "🟢 Активна"
        if user["active"]
        else "🔴 Истекла"
    )

    return (
        "🍑 ПЕРСИК VPN\n\n"
        + status
        + "\n"
        "🟢 Подписка: Free\n"
        "📅 До: "
        + date_text
        + "\n"
        "📦 Трафик: Безлимит\n\n"
        "🔄 Серверы обновляются автоматически\n\n"
        "👇 Выбери действие:"
    )


def subscription_text(user):
    user = refresh_user(
        user["telegram_id"]
    )

    if not user:
        return "❌ Подписка не найдена."

    try:
        expires = datetime.fromisoformat(
            user["expires_at"]
        )

        if expires.tzinfo is None:
            expires = expires.replace(
                tzinfo=timezone.utc
            )

        seconds = (
            expires
            - datetime.now(timezone.utc)
        ).total_seconds()

        days = max(
            0,
            math.ceil(
                seconds / 86400
            )
        )

        date_text = expires.strftime(
            "%d.%m.%Y %H:%M UTC"
        )

    except Exception:
        days = 0
        date_text = "Неизвестно"

    status = (
        "🟢 Активна"
        if user["active"]
        else "🔴 Истекла"
    )

    url = user["subscription_url"]

    if not url:
        url = raw_subscription_url(
            user["token"]
        )

    return (
        "🍑 МОЯ ПОДПИСКА\n\n"
        "🟢 Статус: "
        + status
        + "\n\n"
        "🆓 Тариф: Free\n"
        "📦 Трафик: Безлимит\n"
        "⏳ Осталось дней: "
        + str(days)
        + "\n"
        "📅 До: "
        + date_text
        + "\n\n"
        "🔗 Ссылка подписки:\n"
        + url
    )


@dp.message(CommandStart())
async def start(message: Message):
    user = create_user(
        message.from_user.id,
        message.from_user.username
    )

    try:
        url = await asyncio.to_thread(
            update_github_subscription,
            user
        )

        save_subscription_url(
            message.from_user.id,
            url
        )

        user = get_user(
            message.from_user.id
        )

    except Exception:
        pass

    await message.answer(
        main_text(user),
        reply_markup=main_keyboard(
            message.from_user.id == ADMIN_ID
        )
    )


@dp.callback_query(F.data == "back")
async def back(callback: CallbackQuery):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        user = create_user(
            callback.from_user.id,
            callback.from_user.username
        )

    await callback.message.edit_text(
        main_text(user),
        reply_markup=main_keyboard(
            callback.from_user.id == ADMIN_ID
        )
    )

    await callback.answer()


@dp.callback_query(F.data == "subscription")
async def subscription(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        user = create_user(
            callback.from_user.id,
            callback.from_user.username
        )

    await callback.message.edit_text(
        subscription_text(user),
        reply_markup=subscription_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "refresh")
async def refresh_subscription(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.answer(
            "Подписка не найдена.",
            show_alert=True
        )
        return

    try:
        url = await asyncio.to_thread(
            update_github_subscription,
            user
        )

        user = get_user(
            callback.from_user.id
        )

        try:
            await callback.message.edit_text(
                subscription_text(user),
                reply_markup=subscription_keyboard()
            )
        except Exception as edit_error:
            if "message is not modified" not in str(
                edit_error
            ):
                raise

        await callback.answer(
            "✅ GitHub-подписка обновлена."
        )

    except Exception as error:
        await callback.answer(
            "Ошибка GitHub.",
            show_alert=True
        )

        try:
            await callback.message.edit_text(
                "❌ Ошибка обновления:\n\n"
                + str(error),
                reply_markup=subscription_keyboard()
            )
        except Exception:
            pass


@dp.callback_query(
    F.data == "delete_my_subscription"
)
async def delete_my_subscription(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.answer(
            "Подписка уже удалена.",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        "🗑 УДАЛЕНИЕ ПОДПИСКИ\n\n"
        "Ты действительно хочешь удалить "
        "свою подписку?",
        reply_markup=delete_confirm_keyboard()
    )

    await callback.answer()


@dp.callback_query(
    F.data == "confirm_delete_my_subscription"
)
async def confirm_delete_my_subscription(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.message.edit_text(
            "❌ Подписка уже удалена.",
            reply_markup=back_keyboard()
        )
        await callback.answer()
        return

    try:
        await asyncio.to_thread(
            invalidate_github_subscription,
            user
        )

        delete_user(
            callback.from_user.id
        )

        await callback.message.edit_text(
            "🗑 Подписка удалена.\n\n"
            "☁️ GitHub-файл отключён.",
            reply_markup=back_keyboard()
        )

        await callback.answer(
            "Подписка удалена."
        )

    except Exception as error:
        await callback.message.edit_text(
            "❌ Ошибка удаления:\n\n"
            + str(error),
            reply_markup=back_keyboard()
        )

        await callback.answer()


@dp.callback_query(F.data == "promo")
async def promo_button(
    callback: CallbackQuery
):
    admin_states[
        callback.from_user.id
    ] = "promo_user"

    await callback.message.edit_text(
        "🎟 ПРОМОКОД\n\n"
        "Отправь промокод.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "help")
async def help_button(
    callback: CallbackQuery
):
    await callback.message.edit_text(
        "❓ ПОМОЩЬ\n\n"
        "🍑 Персик VPN — бесплатный VPN.\n\n"
        "📦 Моя подписка — срок и ссылка.\n\n"
        "🔄 Обновить подписку — обновляет "
        "конфигурацию на GitHub.\n\n"
        "🗑 Удалить подписку — отключает "
        "подписку.\n\n"
        "🎟 Промокод — добавить дни.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "admin")
async def admin_panel(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        "🔐 АДМИН-ПАНЕЛЬ\n\n"
        "Выбери действие:",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "admin_users")
async def admin_users(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    users = list_users()

    if not users:
        text = (
            "👥 УЧАСТНИКИ\n\n"
            "Пользователей пока нет."
        )
    else:
        lines = [
            "👥 УЧАСТНИКИ",
            ""
        ]

        for user in users[:100]:
            username = user["username"]

            if username:
                name = "@" + username
            else:
                name = "без username"

            if user["blocked"]:
                status = "🚫"
            elif user["active"]:
                status = "🟢"
            else:
                status = "🔴"

            try:
                expires = datetime.fromisoformat(
                    user["expires_at"]
                )

                date_text = expires.strftime(
                    "%d.%m.%Y"
                )

            except Exception:
                date_text = "?"

            lines.append(
                status
                + " "
                + str(user["telegram_id"])
                + " | "
                + name
                + " | "
                + date_text
            )

        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "admin_add_days")
async def admin_add_days_button(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    admin_states[
        callback.from_user.id
    ] = "add_days"

    await callback.message.edit_text(
        "➕ ВЫДАТЬ ДНИ\n\n"
        "Формат:\n\n"
        "ID ДНИ\n\n"
        "Пример:\n"
        "123456789 30",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "admin_delete")
async def admin_delete_button(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    admin_states[
        callback.from_user.id
    ] = "delete_user"

    await callback.message.edit_text(
        "🗑 УДАЛИТЬ ПОДПИСКУ\n\n"
        "Отправь Telegram ID.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "admin_block")
async def admin_block_button(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    admin_states[
        callback.from_user.id
    ] = "block_user"

    await callback.message.edit_text(
        "🚫 ЗАБЛОКИРОВАТЬ\n\n"
        "Отправь Telegram ID.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "admin_unblock")
async def admin_unblock_button(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    admin_states[
        callback.from_user.id
    ] = "unblock_user"

    await callback.message.edit_text(
        "✅ РАЗБЛОКИРОВАТЬ\n\n"
        "Отправь Telegram ID.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "admin_create_promo")
async def admin_create_promo_button(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    admin_states[
        callback.from_user.id
    ] = "create_promo"

    await callback.message.edit_text(
        "🎟 СОЗДАТЬ ПРОМОКОД\n\n"
        "Формат:\n\n"
        "КОД ДНИ ЛИМИТ\n\n"
        "Пример:\n"
        "FREE30 30 100",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "admin_promos")
async def admin_promos(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    promos = list_promos()

    if not promos:
        text = (
            "📋 ПРОМОКОДЫ\n\n"
            "Промокодов нет."
        )
    else:
        lines = [
            "📋 ПРОМОКОДЫ",
            ""
        ]

        for promo in promos:
            lines.append(
                "🎟 "
                + promo["code"]
                + "\n"
                "⏳ Дней: "
                + str(promo["days"])
                + "\n"
                "👥 Использований: "
                + str(promo["uses"])
                + "/"
                + str(promo["max_uses"])
                + "\n"
            )

        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.message(F.text)
async def text_handler(
    message: Message
):
    user_id = message.from_user.id
    state = admin_states.get(user_id)
    text = message.text.strip()

    if (
        user_id == ADMIN_ID
        and state == "add_days"
    ):
        parts = text.split()

        if len(parts) != 2:
            await message.answer(
                "❌ Формат:\n\n"
                "ID ДНИ"
            )
            return

        try:
            target_id = int(parts[0])
            days = int(parts[1])
        except ValueError:
            await message.answer(
                "❌ ID и дни должны быть числами."
            )
            return

        if days <= 0:
            await message.answer(
                "❌ Дни должны быть больше нуля."
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

        try:
            updated = add_days(
                target_id,
                days
            )

            if not updated:
                raise RuntimeError(
                    "Пользователь исчез из базы."
                )

            await asyncio.to_thread(
                update_github_subscription,
                updated
            )

            updated = get_user(
                target_id
            )

            expires = datetime.fromisoformat(
                updated["expires_at"]
            )

            if expires.tzinfo is None:
                expires = expires.replace(
                    tzinfo=timezone.utc
                )

            expire_unix = int(
                expires.timestamp()
            )

            await message.answer(
                "✅ Дни выданы.\n\n"
                "👤 ID: "
                + str(target_id)
                + "\n"
                "➕ Добавлено: "
                + str(days)
                + " дн.\n"
                "📅 До: "
                + expires.strftime(
                    "%d.%m.%Y %H:%M UTC"
                )
                + "\n"
                "🔢 expire: "
                + str(expire_unix)
                + "\n\n"
                "☁️ TOKEN.txt обновлён "
                "и проверен на GitHub."
            )

        except Exception as error:
            await message.answer(
                "❌ Ошибка выдачи дней:\n\n"
                + str(error)
            )

        admin_states.pop(
            user_id,
            None
        )

        return

    if (
        user_id == ADMIN_ID
        and state == "delete_user"
    ):
        try:
            target_id = int(text)
        except ValueError:
            await message.answer(
                "❌ ID должен быть числом."
            )
            return

        user = get_user(target_id)

        if not user:
            await message.answer(
                "❌ Пользователь не найден."
            )
            return

        try:
            await asyncio.to_thread(
                invalidate_github_subscription,
                user
            )

            delete_user(
                target_id
            )

            await message.answer(
                "🗑 Подписка удалена.\n\n"
                "👤 ID: "
                + str(target_id)
                + "\n"
                "☁️ TOKEN.txt отключён."
            )

        except Exception as error:
            await message.answer(
                "❌ Ошибка удаления:\n\n"
                + str(error)
            )

        admin_states.pop(
            user_id,
            None
        )

        return

    if (
        user_id == ADMIN_ID
        and state == "block_user"
    ):
        try:
            target_id = int(text)
        except ValueError:
            await message.answer(
                "❌ ID должен быть числом."
            )
            return

        user = get_user(target_id)

        if not user:
            await message.answer(
                "❌ Пользователь не найден."
            )
            return

        try:
            set_blocked(
                target_id,
                True
            )

            updated = get_user(
                target_id
            )

            await asyncio.to_thread(
                invalidate_github_subscription,
                updated
            )

            await message.answer(
                "🚫 Пользователь заблокирован.\n\n"
                "☁️ TOKEN.txt отключён."
            )

        except Exception as error:
            await message.answer(
                "❌ Ошибка блокировки:\n\n"
                + str(error)
            )

        admin_states.pop(
            user_id,
            None
        )

        return

    if (
        user_id == ADMIN_ID
        and state == "unblock_user"
    ):
        try:
            target_id = int(text)
        except ValueError:
            await message.answer(
                "❌ ID должен быть числом."
            )
            return

        user = get_user(target_id)

        if not user:
            await message.answer(
                "❌ Пользователь не найден."
            )
            return

        try:
            set_blocked(
                target_id,
                False
            )

            updated = get_user(
                target_id
            )

            await asyncio.to_thread(
                update_github_subscription,
                updated
            )

            await message.answer(
                "✅ Пользователь разблокирован.\n\n"
                "☁️ TOKEN.txt восстановлен "
                "с актуальным expire."
            )

        except Exception as error:
            await message.answer(
                "❌ Ошибка разблокировки:\n\n"
                + str(error)
            )

        admin_states.pop(
            user_id,
            None
        )

        return

    if (
        user_id == ADMIN_ID
        and state == "create_promo"
    ):
        parts = text.split()

        if len(parts) != 3:
            await message.answer(
                "❌ Формат:\n\n"
                "КОД ДНИ ЛИМИТ"
            )
            return

        code = parts[0].strip().upper()

        try:
            days = int(parts[1])
            max_uses = int(parts[2])
        except ValueError:
            await message.answer(
                "❌ Дни и лимит должны быть числами."
            )
            return

        if days <= 0 or max_uses <= 0:
            await message.answer(
                "❌ Значения должны быть больше нуля."
            )
            return

        try:
            create_promo(
                code,
                days,
                max_uses
            )

            await message.answer(
                "✅ Промокод создан.\n\n"
                "🎟 "
                + code
                + "\n"
                "⏳ "
                + str(days)
                + " дн.\n"
                "👥 Лимит: "
                + str(max_uses)
            )

        except Exception as error:
            await message.answer(
                "❌ Ошибка создания промокода:\n\n"
                + str(error)
            )

        admin_states.pop(
            user_id,
            None
        )

        return

    if state == "promo_user":
        success, result = use_promo(
            text,
            user_id
        )

        if not success:
            await message.answer(
                "❌ " + str(result)
            )
            return

        days = int(result)

        user = get_user(
            user_id
        )

        if not user:
            user = create_user(
                user_id,
                message.from_user.username
            )

        try:
            updated = add_days(
                user_id,
                days
            )

            await asyncio.to_thread(
                update_github_subscription,
                updated
            )

            updated = get_user(
                user_id
            )

            await message.answer(
                "🎉 Промокод активирован!\n\n"
                "➕ Добавлено: "
                + str(days)
                + " дн.\n\n"
                + subscription_text(
                    updated
                ),
                reply_markup=subscription_keyboard()
            )

        except Exception as error:
            await message.answer(
                "❌ Ошибка обновления подписки:\n\n"
                + str(error)
            )

        admin_states.pop(
            user_id,
            None
        )

        return

    user = get_user(
        user_id
    )

    if not user:
        user = create_user(
            user_id,
            message.from_user.username
        )

    await message.answer(
        main_text(user),
        reply_markup=main_keyboard(
            user_id == ADMIN_ID
        )
    )


async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не задан"
        )

    init_db()

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":
    asyncio.run(main())
