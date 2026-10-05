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

from config import (
    BOT_TOKEN,
    ADMIN_ID,
)

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
)

from github_api import (
    put_file,
    delete_file,
    raw_subscription_url,
    subscription_path,
)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =========================================================
# НАСТРОЙКИ
# =========================================================

PROFILE_TITLE = "🍑 Персик VPN"

ANNOUNCE = (
    "🆓 Бесплатный VPN | "
    "🇳🇱 Нидерланды • "
    "🇩🇪 Германия • "
    "🇰🇿 Казахстан"
)

UPDATE_INTERVAL = 1

NODES_FILE = "nodes.txt"


# =========================================================
# КЛАВИАТУРЫ
# =========================================================

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
                text="🔄 Обновить подписку",
                callback_data="refresh"
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


# =========================================================
# СОСТОЯНИЕ АДМИНА
# =========================================================

admin_states = {}


# =========================================================
# NODES
# =========================================================

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


# =========================================================
# ПОДПИСКА
# =========================================================

def get_expire_timestamp(user):
    expires_at = datetime.fromisoformat(
        user["expires_at"]
    )

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(
            tzinfo=timezone.utc
        )

    return int(
        expires_at.timestamp()
    )


def build_subscription(user):
    expire = get_expire_timestamp(user)

    nodes = load_nodes()

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
        "#profile-update-interval: "
        + str(UPDATE_INTERVAL),
        "",
    ]

    lines.extend(nodes)

    lines.append("")

    return "\n".join(lines)


def github_update_subscription(user):
    token = user["token"]

    content = build_subscription(
        user
    )

    path = subscription_path(
        token
    )

    put_file(
        path,
        content,
        "Update subscription "
        + str(user["telegram_id"])
    )

    return raw_subscription_url(
        token
    )


def github_invalidate_subscription(user):
    token = user["token"]

    path = subscription_path(
        token
    )

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

    put_file(
        path,
        content,
        "Disable subscription "
        + str(user["telegram_id"])
    )


# =========================================================
# ТЕКСТ ГЛАВНОГО МЕНЮ
# =========================================================

def main_text(user):
    user = refresh_user(
        user["telegram_id"]
    )

    if not user:
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "Пользователь не найден."
        )

    if user["blocked"]:
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "🚫 Твоя подписка заблокирована."
        )

    try:
        expires = datetime.fromisoformat(
            user["expires_at"]
        )

        now = datetime.now(
            timezone.utc
        )

        seconds = (
            expires - now
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
        "🆓 Подписка: Free\n"
        "📅 До: "
        + date_text
        + "\n"
        "📦 Трафик: Безлимит\n\n"
        "🔄 Серверы обновляются автоматически\n\n"
        "👇 Выбери действие:"
    )


# =========================================================
# СТРАНИЦА ПОДПИСКИ
# =========================================================

def subscription_text(user):
    user = refresh_user(
        user["telegram_id"]
    )

    if not user:
        return (
            "❌ Подписка не найдена."
        )

    try:
        expires = datetime.fromisoformat(
            user["expires_at"]
        )

        now = datetime.now(
            timezone.utc
        )

        seconds = (
            expires - now
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


# =========================================================
# ГЛАВНОЕ МЕНЮ
# =========================================================

@dp.message(CommandStart())
async def start(message: Message):
    user = create_user(
        message.from_user.id,
        message.from_user.username
    )

    try:
        url = await asyncio.to_thread(
            github_update_subscription,
            user
        )

        current = get_user(
            message.from_user.id
        )

        if current and current["subscription_url"] != url:
            from database import save_subscription_url

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


# =========================================================
# CALLBACK: НАЗАД
# =========================================================

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


# =========================================================
# МОЯ ПОДПИСКА
# =========================================================

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
        reply_markup=back_keyboard()
    )

    await callback.answer()


# =========================================================
# ОБНОВИТЬ ПОДПИСКУ
# =========================================================

@dp.callback_query(F.data == "refresh")
async def refresh_subscription(
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

    try:
        url = await asyncio.to_thread(
            github_update_subscription,
            user
        )

        from database import save_subscription_url

        save_subscription_url(
            callback.from_user.id,
            url
        )

        user = get_user(
            callback.from_user.id
        )

        await callback.message.edit_text(
            "✅ Подписка обновлена.\n\n"
            "Новая версия подписки уже "
            "загружена на GitHub.\n\n"
            + subscription_text(user),
            reply_markup=back_keyboard()
        )

    except Exception as error:
        await callback.message.edit_text(
            "❌ Не удалось обновить подписку.\n\n"
            + str(error),
            reply_markup=back_keyboard()
        )

    await callback.answer()


# =========================================================
# ПРОМОКОД
# =========================================================

@dp.callback_query(F.data == "promo")
async def promo_button(
    callback: CallbackQuery
):
    await callback.message.edit_text(
        "🎟 ПРОМОКОД\n\n"
        "Отправь промокод следующим сообщением.",
        reply_markup=back_keyboard()
    )

    admin_states[
        callback.from_user.id
    ] = "promo_user"

    await callback.answer()


# =========================================================
# ПОМОЩЬ
# =========================================================

@dp.callback_query(F.data == "help")
async def help_button(
    callback: CallbackQuery
):
    await callback.message.edit_text(
        "❓ ПОМОЩЬ\n\n"
        "🍑 Персик VPN — бесплатный VPN.\n\n"
        "📦 Моя подписка — посмотреть срок "
        "и ссылку подписки.\n\n"
        "🔄 Обновить подписку — вручную "
        "обновить конфигурацию.\n\n"
        "🎟 Промокод — активировать код "
        "на дополнительные дни.\n\n"
        "Если сервер временно не работает, "
        "обнови подписку позже.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


# =========================================================
# АДМИН-ПАНЕЛЬ
# =========================================================

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


# =========================================================
# УЧАСТНИКИ
# =========================================================

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
            "Пока нет пользователей."
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

            status = (
                "🚫"
                if user["blocked"]
                else (
                    "🟢"
                    if user["active"]
                    else "🔴"
                )
            )

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


# =========================================================
# ВЫДАТЬ ДНИ
# =========================================================

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
        "Отправь:\n\n"
        "ID количество_дней\n\n"
        "Пример:\n"
        "8847877937 30",
        reply_markup=back_keyboard()
    )

    await callback.answer()


# =========================================================
# УДАЛИТЬ ПОДПИСКУ
# =========================================================

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
        "Отправь Telegram ID пользователя.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


# =========================================================
# БЛОКИРОВКА
# =========================================================

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
        "Отправь Telegram ID пользователя.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


# =========================================================
# РАЗБЛОКИРОВКА
# =========================================================

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
        "Отправь Telegram ID пользователя.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


# =========================================================
# СОЗДАТЬ ПРОМОКОД
# =========================================================

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
        "Отправь:\n\n"
        "КОД ДНИ КОЛИЧЕСТВО_ИСПОЛЬЗОВАНИЙ\n\n"
        "Пример:\n"
        "FREE30 30 100",
        reply_markup=back_keyboard()
    )

    await callback.answer()


# =========================================================
# СПИСОК ПРОМОКОДОВ
# =========================================================

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
            "Промокодов пока нет."
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


# =========================================================
# ОБРАБОТКА ТЕКСТА
# =========================================================

@dp.message(F.text)
async def text_handler(
    message: Message
):
    user_id = message.from_user.id

    state = admin_states.get(
        user_id
    )

    text = message.text.strip()

    # -----------------------------------------------------
    # АДМИН: ВЫДАТЬ ДНИ
    # -----------------------------------------------------

    if (
        user_id == ADMIN_ID
        and state == "add_days"
    ):
        parts = text.split()

        if len(parts) != 2:
            await message.answer(
                "❌ Формат:\n\n"
                "ID количество_дней\n\n"
                "Пример:\n"
                "8847877937 30"
            )
            return

        try:
            target_id = int(
                parts[0]
            )

            days = int(
                parts[1]
            )

        except ValueError:
            await message.answer(
                "❌ ID и количество дней "
                "должны быть числами."
            )
            return

        if days <= 0:
            await message.answer(
                "❌ Количество дней должно "
                "быть больше нуля."
            )
            return

        target = get_user(
            target_id
        )

        if not target:
            await message.answer(
                "❌ Пользователь не найден."
            )
            return

        try:
            # 1. Меняем срок в БД
            updated = add_days(
                target_id,
                days
            )

            # 2. Берём уже обновлённого
            # пользователя
            updated = get_user(
                target_id
            )

            # 3. СРАЗУ перезаписываем
            # GitHub subscription
            url = await asyncio.to_thread(
                github_update_subscription,
                updated
            )

            # 4. Сохраняем URL
            from database import save_subscription_url

            save_subscription_url(
                target_id,
                url
            )

            # 5. Берём свежие данные
            updated = get_user(
                target_id
            )

            expires = datetime.fromisoformat(
                updated["expires_at"]
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
                "☁️ GitHub подписка обновлена.\n"
                "🔗 URL остался прежним."
            )

        except Exception as error:
            await message.answer(
                "❌ Дни изменились в базе, "
                "но GitHub не обновился.\n\n"
                + str(error)
            )

        admin_states.pop(
            user_id,
            None
        )

        return

    # -----------------------------------------------------
    # АДМИН: УДАЛИТЬ
    # -----------------------------------------------------

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

        target = get_user(
            target_id
        )

        if not target:
            await message.answer(
                "❌ Пользователь не найден."
            )
            return

        try:
            await asyncio.to_thread(
                github_invalidate_subscription,
                target
            )
        except Exception as error:
            await message.answer(
                "❌ Не удалось отключить "
                "подписку на GitHub.\n\n"
                + str(error)
            )
            return

        delete_user(
            target_id
        )

        await message.answer(
            "🗑 Подписка удалена.\n\n"
            "ID: "
            + str(target_id)
            + "\n\n"
            "Ссылка на GitHub больше "
            "не содержит активные серверы."
        )

        admin_states.pop(
            user_id,
            None
        )

        return

    # -----------------------------------------------------
    # АДМИН: БЛОК
    # -----------------------------------------------------

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

        target = get_user(
            target_id
        )

        if not target:
            await message.answer(
                "❌ Пользователь не найден."
            )
            return

        try:
            await asyncio.to_thread(
                github_invalidate_subscription,
                target
            )
        except Exception as error:
            await message.answer(
                "❌ Ошибка GitHub:\n"
                + str(error)
            )
            return

        set_blocked(
            target_id,
            True
        )

        await message.answer(
            "🚫 Пользователь заблокирован.\n\n"
            "ID: "
            + str(target_id)
        )

        admin_states.pop(
            user_id,
            None
        )

        return

    # -----------------------------------------------------
    # АДМИН: РАЗБЛОК
    # -----------------------------------------------------

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

        target = get_user(
            target_id
        )

        if not target:
            await message.answer(
                "❌ Пользователь не найден."
            )
            return

        updated = set_blocked(
            target_id,
            False
        )

        try:
            updated = get_user(
                target_id
            )

            url = await asyncio.to_thread(
                github_update_subscription,
                updated
            )

            from database import save_subscription_url

            save_subscription_url(
                target_id,
                url
            )

        except Exception as error:
            await message.answer(
                "⚠️ Пользователь разблокирован, "
                "но GitHub не обновился.\n\n"
                + str(error)
            )

            admin_states.pop(
                user_id,
                None
            )

            return

        await message.answer(
            "✅ Пользователь разблокирован.\n\n"
            "ID: "
            + str(target_id)
            + "\n"
            "☁️ Подписка обновлена."
        )

        admin_states.pop(
            user_id,
            None
        )

        return

    # -----------------------------------------------------
    # АДМИН: ПРОМОКОД
    # -----------------------------------------------------

    if (
        user_id == ADMIN_ID
        and state == "create_promo"
    ):
        parts = text.split()

        if len(parts) != 3:
            await message.answer(
                "❌ Формат:\n\n"
                "КОД ДНИ КОЛИЧЕСТВО\n\n"
                "Пример:\n"
                "FREE30 30 100"
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

        except ValueError:
            await message.answer(
                "❌ Дни и количество "
                "использований должны "
                "быть числами."
            )
            return

        if days <= 0 or max_uses <= 0:
            await message.answer(
                "❌ Дни и количество "
                "использований должны "
                "быть больше нуля."
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
                "🎟 Код: "
                + code.upper()
                + "\n"
                "⏳ Дней: "
                + str(days)
                + "\n"
                "👥 Использований: "
                + str(max_uses)
            )

        except Exception as error:
            await message.answer(
                "❌ Ошибка создания промокода:\n"
                + str(error)
            )

        admin_states.pop(
            user_id,
            None
        )

        return

    # -----------------------------------------------------
    # ПОЛЬЗОВАТЕЛЬ: ПРОМОКОД
    # -----------------------------------------------------

    if state == "promo_user":
        success, result = use_promo(
            text,
            user_id
        )

        if not success:
            await message.answer(
                "❌ "
                + str(result)
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

            updated = get_user(
                user_id
            )

            url = await asyncio.to_thread(
                github_update_subscription,
                updated
            )

            from database import save_subscription_url

            save_subscription_url(
                user_id,
                url
            )

            await message.answer(
                "🎉 Промокод активирован!\n\n"
                "➕ Добавлено: "
                + str(days)
                + " дн.\n\n"
                + subscription_text(
                    updated
                ),
                reply_markup=main_keyboard(
                    user_id == ADMIN_ID
                )
            )

        except Exception as error:
            await message.answer(
                "❌ Дни начислены, "
                "но подписка не обновилась.\n\n"
                + str(error)
            )

        admin_states.pop(
            user_id,
            None
        )

        return

    # -----------------------------------------------------
    # НЕИЗВЕСТНЫЙ ТЕКСТ
    # -----------------------------------------------------

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


# =========================================================
# ЗАПУСК
# =========================================================

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
