import asyncio
import os
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart

from config import (
    BOT_TOKEN,
    ADMIN_ID,
    EXPIRE_DAYS,
    HAPP_PAGE,
)

from database import (
    init_db,
    get_user,
    create_user,
    save_subscription_url,
    new_token,
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

admin_states = {}


PROFILE_TITLE = "🍑 Персик VPN"

ANNOUNCE = (
    "🆓 Бесплатный VPN | "
    "🇳🇱 Нидерланды • "
    "🇩🇪 Германия • "
    "🇰🇿 Казахстан"
)

UPDATE_INTERVAL = "#profile-update-interval: 1"

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

NODES_FILE = os.path.join(
    BASE_DIR,
    "nodes.txt"
)


def load_nodes():
    if not os.path.exists(NODES_FILE):
        return ""

    with open(
        NODES_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        lines = file.readlines()

    result = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith("#"):
            continue

        result.append(stripped)

    return "\n".join(result)


def unix_expire(expires_at):
    try:
        dt = datetime.fromisoformat(
            expires_at
        )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return int(dt.timestamp())

    except Exception:
        return 0


def format_date(expires_at):
    try:
        dt = datetime.fromisoformat(
            expires_at
        )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.strftime(
            "%d.%m.%Y %H:%M"
        )

    except Exception:
        return "Н/Д"


def make_subscription(user):
    token = user["token"]

    nodes = load_nodes()

    if not nodes:
        raise RuntimeError(
            "nodes.txt пуст или не найден"
        )

    content = (
        'id="{}"\n'
        "{}\n"
        "{}\n"
        "#subscription-userinfo: "
        "upload=0; "
        "download={}; "
        "expire={}\n"
        "{}\n\n"
        "{}\n"
    ).format(
        token[:6],
        PROFILE_TITLE,
        ANNOUNCE,
        user["total_bytes"],
        unix_expire(
            user["expires_at"]
        ),
        UPDATE_INTERVAL,
        nodes
    )

    path = subscription_path(token)

    put_file(
        path,
        content,
        "Update subscription"
    )

    return raw_subscription_url(token)


def user_keyboard():
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
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
                ),
                types.InlineKeyboardButton(
                    text="❓ Помощь",
                    callback_data="help"
                )
            ],
        ]
    )


def subscription_keyboard():
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="🔄 Обновить",
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
                    text="⬅️ Назад",
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
                ),
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
                    text="⬅️ Назад",
                    callback_data="back"
                )
            ],
        ]
    )


async def send_subscription(
    message,
    telegram_id
):
    user = refresh_user(
        telegram_id
    )

    if not user:
        user = create_user(
            telegram_id,
            message.from_user.username
            if message.from_user
            else ""
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
                "Попробуй позже.\n\n"
                "Ошибка: "
                + str(error)
            )
            return

    text = (
        "🍑 Твоя подписка\n\n"
        "📦 Безлимитный трафик\n"
        "📅 До: "
        + format_date(
            user["expires_at"]
        )
        + "\n\n"
        "🔗 Ссылка подписки:\n"
        + user["subscription_url"]
    )

    await message.answer(
        text,
        reply_markup=subscription_keyboard()
    )


@dp.message(CommandStart())
async def start(message: types.Message):
    user = get_user(
        message.from_user.id
    )

    if not user:
        user = create_user(
            message.from_user.id,
            message.from_user.username or ""
        )

        await message.answer(
            "🍑 Персик VPN\n\n"
            "Добро пожаловать!\n\n"
            "🆓 Бесплатная подписка\n"
            "📦 Безлимитный трафик\n"
            "📅 Срок: 7 дней",
            reply_markup=user_keyboard()
        )

        await send_subscription(
            message,
            message.from_user.id
        )

    else:
        await message.answer(
            "🍑 Персик VPN\n\n"
            "С возвращением!\n"
            "Выбери действие:",
            reply_markup=user_keyboard()
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
            "Сначала нажми /start"
        )
        return

    if user["blocked"]:
        await callback.message.answer(
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
                callback.from_user.id,
                url
            )

            user = get_user(
                callback.from_user.id
            )

        except Exception as error:
            await callback.message.answer(
                "❌ Ошибка создания подписки:\n"
                + str(error)
            )
            return

    await callback.message.answer(
        "🍑 Моя подписка\n\n"
        "📦 Безлимитный трафик\n"
        "📅 До: "
        + format_date(
            user["expires_at"]
        )
        + "\n\n"
        "🔗 "
        + user["subscription_url"],
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
            "Сначала нажми /start"
        )
        return

    try:
        url = await asyncio.to_thread(
            make_subscription,
            user
        )

        save_subscription_url(
            callback.from_user.id,
            url
        )

        await callback.message.answer(
            "✅ Подписка обновлена!\n\n"
            "🔗 "
            + url,
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
        "Файл подписки будет удалён с GitHub, "
        "а ссылка перестанет работать.",
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
            "У тебя нет подписки."
        )
        return

    try:
        if user["token"]:
            await asyncio.to_thread(
                delete_file,
                subscription_path(
                    user["token"]
                ),
                "Delete subscription"
            )

    except Exception:
        pass

    delete_user(
        callback.from_user.id
    )

    await callback.message.answer(
        "🗑 Подписка удалена.\n\n"
        "Чтобы создать новую, нажми /start.",
        reply_markup=user_keyboard()
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
        "❓ Помощь\n\n"
        "1. Нажми «Моя подписка».\n"
        "2. Скопируй ссылку.\n"
        "3. Добавь её в Happ.\n\n"
        "🔄 Если серверы изменились, "
        "нажми «Обновить».\n\n"
        "🎟 Если у тебя есть промокод, "
        "открой раздел «Промокод»."
    )


@dp.callback_query(
    F.data == "back"
)
async def back(
    callback: types.CallbackQuery
):
    await callback.answer()

    if callback.from_user.id == ADMIN_ID:
        await callback.message.answer(
            "🔐 Админ-панель",
            reply_markup=admin_keyboard()
        )
    else:
        await callback.message.answer(
            "🍑 Персик VPN",
            reply_markup=user_keyboard()
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

    await callback.message.answer(
        "🔐 Админ-панель",
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
        "🔐 Админ-панель",
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
            "👥 Пользователей пока нет."
        )
        return

    lines = [
        "👥 Пользователи:\n"
    ]

    for user in users:
        username = user["username"] or "без username"

        status = (
            "🚫 заблокирован"
            if user["blocked"]
            else (
                "🟢 активна"
                if user["active"]
                else "🔴 истекла"
            )
        )

        lines.append(
            "ID: "
            + str(user["telegram_id"])
            + "\n@"
            + username.lstrip("@")
            + "\n"
            + status
            + "\nДо: "
            + format_date(
                user["expires_at"]
            )
            + "\n"
        )

    await callback.message.answer(
        "\n".join(lines)
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
        "🎟 Создание промокода\n\n"
        "Отправь в формате:\n"
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
            "🎟 Промокодов пока нет."
        )
        return

    lines = [
        "🎟 Промокоды:\n"
    ]

    for promo in promos:
        lines.append(
            "Код: "
            + promo["code"]
            + "\n"
            + "Дни: "
            + str(promo["days"])
            + "\n"
            + "Использований: "
            + str(promo["uses"])
            + "/"
            + str(promo["max_uses"])
            + "\n"
        )

    await callback.message.answer(
        "\n".join(lines)
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
        "➕ Выдать дни\n\n"
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
        "🗑 Удаление подписки\n\n"
        "Отправь Telegram ID пользователя."
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
        "🚫 Блокировка\n\n"
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
        "✅ Разблокировка\n\n"
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
                days = int(parts[1])
                max_uses = int(parts[2])

                if days <= 0:
                    raise ValueError

                if max_uses <= 0:
                    raise ValueError

            except ValueError:
                await message.answer(
                    "❌ Дни и лимит должны быть "
                    "положительными числами."
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
                    "✅ Промокод создан!\n\n"
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
                    "❌ Ошибка создания промокода:\n"
                    + str(error)
                )

            return

        if state == "admin_days":
            parts = text.split()

            if len(parts) != 2:
                await message.answer(
                    "❌ Формат:\nID ДНИ"
                )
                return

            try:
                target_id = int(parts[0])
                days = int(parts[1])

                if days <= 0:
                    raise ValueError

            except ValueError:
                await message.answer(
                    "❌ Формат:\nID ДНИ"
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
                    "⚠️ Дни выданы, но GitHub "
                    "не обновился:\n"
                    + str(error),
                    reply_markup=admin_keyboard()
                )
                return

            await message.answer(
                "✅ Выдано дней: "
                + str(days)
                + "\n"
                "👤 ID: "
                + str(target_id)
                + "\n"
                "📅 До: "
                + format_date(
                    user["expires_at"]
                ),
                reply_markup=admin_keyboard()
            )

            return

        if state == "admin_delete":
            try:
                target_id = int(text)
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
                if user["token"]:
                    await asyncio.to_thread(
                        delete_file,
                        subscription_path(
                            user["token"]
                        ),
                        "Admin delete subscription"
                    )
            except Exception:
                pass

            delete_user(
                target_id
            )

            await message.answer(
                "🗑 Подписка удалена.\n"
                "ID: "
                + str(target_id),
                reply_markup=admin_keyboard()
            )

            return

        if state in (
            "admin_block",
            "admin_unblock"
        ):
            try:
                target_id = int(text)
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
                    if user["token"]:
                        await asyncio.to_thread(
                            delete_file,
                            subscription_path(
                                user["token"]
                            ),
                            "Block user subscription"
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
                + "\nID: "
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
                reply_markup=user_keyboard()
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
            "🎉 Промокод активирован!\n\n"
            "📅 Добавлено дней: "
            + str(days)
            + "\n"
            "📅 Подписка до: "
            + format_date(
                updated["expires_at"]
            ),
            reply_markup=user_keyboard()
        )

        return

    await message.answer(
        "🍑 Персик VPN\n\n"
        "Используй кнопки меню.",
        reply_markup=user_keyboard()
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

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
