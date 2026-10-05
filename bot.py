import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import (
    BOT_TOKEN,
    ADMIN_ID
)

from database import (
    init_db,
    get_user,
    create_user,
    save_subscription_url,
    refresh_user,
    list_users,
    set_blocked
)

from github_api import (
    get_file_content,
    put_file_verified,
    subscription_path,
    raw_subscription_url
)


# ============================================================
# SETTINGS
# ============================================================

TOTAL_BYTES = 10737418240

NODES_FILE = "nodes.txt"


# ============================================================
# BOT
# ============================================================

bot = Bot(
    token=BOT_TOKEN
)

dp = Dispatcher()


# ============================================================
# STATES
# ============================================================

class AdminStates(StatesGroup):
    block_user = State()
    unblock_user = State()


# ============================================================
# HELPERS
# ============================================================

def is_admin(
    user_id
):
    return int(user_id) == int(
        ADMIN_ID
    )


def username_of(
    message
):
    if not message.from_user:
        return ""

    return (
        message.from_user.username
        or ""
    )


# ============================================================
# NODES
# ============================================================

def read_nodes():
    if not os.path.exists(
        NODES_FILE
    ):
        return []

    try:
        with open(
            NODES_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            lines = file.read().splitlines()

    except Exception:
        return []

    result = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        result.append(line)

    return result


# ============================================================
# SUBSCRIPTION
# ============================================================

def build_subscription(
    user
):
    lines = [
        'id="' + user["token"][:6] + '"',

        "#profile-title: 🍑 Персик VPN",

        "#announce: 🆓 Бесплатный VPN | "
        "🇳🇱 Нидерланды • "
        "🇩🇪 Германия • "
        "🇰🇿 Казахстан",

        "#subscription-userinfo: "
        "upload=0; "
        "download=0; "
        "total="
        + str(TOTAL_BYTES),

        "#profile-update-interval: 1",

        ""
    ]

    lines.extend(
        read_nodes()
    )

    lines.append("")

    return "\n".join(
        lines
    )


def create_or_check_subscription(
    user
):
    path = subscription_path(
        user["token"]
    )

    existing = get_file_content(
        path
    )

    if existing:
        return (
            existing,
            False
        )

    content = build_subscription(
        user
    )

    put_file_verified(
        path,
        content,
        "Create permanent subscription "
        + str(user["telegram_id"])
    )

    return (
        content,
        True
    )


def check_subscription(
    user
):
    path = subscription_path(
        user["token"]
    )

    content = get_file_content(
        path
    )

    if not content:
        return False

    # Проверяем, что файл реально содержит
    # subscription-userinfo.
    if "#subscription-userinfo:" not in content:
        return False

    # Проверяем лимит 10 ГБ.
    expected = (
        "total="
        + str(TOTAL_BYTES)
    )

    if expected not in content:
        return False

    return True


def update_subscription(
    user
):
    content = build_subscription(
        user
    )

    put_file_verified(
        subscription_path(
            user["token"]
        ),
        content,
        "Update permanent subscription "
        + str(user["telegram_id"])
    )

    return True


# ============================================================
# TEXT
# ============================================================

def main_text(
    user
):
    if user["blocked"]:
        status = "🔴 Заблокирована"
    else:
        status = "🟢 Подписка: Free"

    return (
        "🍑 ПЕРСИК VPN\n\n"
        + status
        + "\n"
        + "📅 Срок: ♾️ Безлимит\n"
        + "📦 Трафик: 10 ГБ\n\n"
        + "🔄 Серверы обновляются автоматически\n\n"
        + "👇 Выбери действие:"
    )


def subscription_text(
    user,
    ok=True
):
    url = user["subscription_url"]

    if not url:
        url = raw_subscription_url(
            user["token"]
        )

    if ok:
        status = "🟢 Подписка OK"
    else:
        status = "🔴 Ошибка проверки"

    return (
        "📦 МОЯ ПОДПИСКА\n\n"
        + status
        + "\n\n"
        + "📦 Трафик: 10 ГБ\n"
        + "📅 Срок: ♾️ Безлимит\n\n"
        + "🔗 Постоянная ссылка:\n"
        + url
    )


# ============================================================
# KEYBOARDS
# ============================================================

def main_keyboard(
    user_id
):
    buttons = [
        [
            InlineKeyboardButton(
                text="📦 Моя подписка",
                callback_data="subscription"
            )
        ],
        [
            InlineKeyboardButton(
                text="❓ Помощь",
                callback_data="help"
            )
        ]
    ]

    if is_admin(
        user_id
    ):
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🔐 Админ-панель",
                    callback_data="admin"
                )
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


def subscription_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Проверить подписку",
                    callback_data="refresh_subscription"
                )
            ],
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
                    text="👥 Пользователи",
                    callback_data="admin_users"
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
                    text="🟢 Разблокировать",
                    callback_data="admin_unblock"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="back"
                )
            ]
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


# ============================================================
# START
# ============================================================

@dp.message(
    CommandStart()
)
async def start(
    message: Message
):
    user_id = message.from_user.id

    user = create_user(
        user_id,
        username_of(message)
    )

    if not user:
        await message.answer(
            "❌ Не удалось создать пользователя."
        )
        return

    if user["blocked"]:
        await message.answer(
            "🚫 Твоя подписка заблокирована."
        )
        return

    try:
        url = raw_subscription_url(
            user["token"]
        )

        # Один пользователь = один URL.
        if not user["subscription_url"]:
            save_subscription_url(
                user_id,
                url
            )

            user = get_user(
                user_id
            )

        # Создаём TOKEN.txt только если
        # его ещё нет.
        create_or_check_subscription(
            user
        )

        user = refresh_user(
            user_id
        )

        await message.answer(
            main_text(user),
            reply_markup=main_keyboard(
                user_id
            )
        )

    except Exception as error:
        await message.answer(
            "❌ Ошибка создания подписки:\n\n"
            + str(error)
        )


# ============================================================
# BACK
# ============================================================

@dp.callback_query(
    F.data == "back"
)
async def back(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        user = create_user(
            callback.from_user.id,
            callback.from_user.username or ""
        )

    try:
        await callback.message.edit_text(
            main_text(user),
            reply_markup=main_keyboard(
                callback.from_user.id
            )
        )

    except Exception as error:
        if "message is not modified" not in str(error).lower():
            raise

    await callback.answer()


# ============================================================
# SUBSCRIPTION
# ============================================================

@dp.callback_query(
    F.data == "subscription"
)
async def subscription(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        user = create_user(
            callback.from_user.id,
            callback.from_user.username or ""
        )

    if user["blocked"]:
        await callback.answer(
            "🚫 Подписка заблокирована.",
            show_alert=True
        )
        return

    try:
        ok = check_subscription(
            user
        )

        if not user["subscription_url"]:
            save_subscription_url(
                callback.from_user.id,
                raw_subscription_url(
                    user["token"]
                )
            )

            user = get_user(
                callback.from_user.id
            )

        await callback.message.edit_text(
            subscription_text(
                user,
                ok
            ),
            reply_markup=subscription_keyboard()
        )

        if ok:
            await callback.answer(
                "✅ Проверка OK"
            )
        else:
            await callback.answer(
                "❌ TOKEN.txt не найден или повреждён.",
                show_alert=True
            )

    except Exception as error:
        await callback.answer(
            "❌ Ошибка проверки.",
            show_alert=True
        )

        await callback.message.answer(
            "❌ Ошибка:\n\n"
            + str(error)
        )


# ============================================================
# REFRESH / CHECK
# ============================================================

@dp.callback_query(
    F.data == "refresh_subscription"
)
async def refresh_subscription(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.answer(
            "❌ Пользователь не найден.",
            show_alert=True
        )
        return

    if user["blocked"]:
        await callback.answer(
            "🚫 Подписка заблокирована.",
            show_alert=True
        )
        return

    try:
        ok = check_subscription(
            user
        )

        if not ok:
            # Если TOKEN.txt пропал,
            # восстанавливаем его с тем же TOKEN.
            update_subscription(
                user
            )

            ok = check_subscription(
                user
            )

        user = get_user(
            callback.from_user.id
        )

        await callback.message.edit_text(
            subscription_text(
                user,
                ok
            ),
            reply_markup=subscription_keyboard()
        )

        if ok:
            await callback.answer(
                "✅ Всё OK"
            )
        else:
            await callback.answer(
                "❌ Проверка не пройдена.",
                show_alert=True
            )

    except Exception as error:
        await callback.answer(
            "❌ Ошибка проверки.",
            show_alert=True
        )

        await callback.message.answer(
            "❌ Ошибка:\n\n"
            + str(error)
        )


# ============================================================
# HELP
# ============================================================

@dp.callback_query(
    F.data == "help"
)
async def help_callback(
    callback: CallbackQuery
):
    await callback.message.edit_text(
        "❓ ПОМОЩЬ\n\n"
        "🍑 Персик VPN\n\n"
        "📦 Трафик: 10 ГБ\n"
        "📅 Срок: ♾️ Безлимит\n"
        "🔗 Ссылка постоянная.\n\n"
        "Добавь ссылку из «Моя подписка» "
        "в Happ.\n\n"
        "Если подписка не обновилась, "
        "нажми «🔄 Проверить подписку».",
        reply_markup=back_keyboard()
    )

    await callback.answer()


# ============================================================
# ADMIN PANEL
# ============================================================

@dp.callback_query(
    F.data == "admin"
)
async def admin_panel(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        "🔐 АДМИН-ПАНЕЛЬ\n\n"
        "Выбери действие:",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


# ============================================================
# ADMIN USERS
# ============================================================

@dp.callback_query(
    F.data == "admin_users"
)
async def admin_users(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    users = list_users()

    if not users:
        text = (
            "👥 ПОЛЬЗОВАТЕЛИ\n\n"
            "Пользователей пока нет."
        )

    else:
        lines = [
            "👥 ПОЛЬЗОВАТЕЛИ",
            ""
        ]

        for user in users:
            if user["blocked"]:
                status = "🚫"
            else:
                status = "🟢"

            username = (
                "@"
                + user["username"]
                if user["username"]
                else "без username"
            )

            lines.append(
                status
                + " "
                + str(user["telegram_id"])
                + " "
                + username
            )

            lines.append(
                "🔗 TOKEN: "
                + user["token"]
            )

            lines.append("")

        text = "\n".join(
            lines
        )

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard()
    )

    await callback.answer()


# ============================================================
# ADMIN BLOCK
# ============================================================

@dp.callback_query(
    F.data == "admin_block"
)
async def admin_block_start(
    callback: CallbackQuery,
    state: FSMContext
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    await state.set_state(
        AdminStates.block_user
    )

    await callback.message.edit_text(
        "🚫 БЛОКИРОВКА\n\n"
        "Отправь Telegram ID.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.message(
    AdminStates.block_user
)
async def admin_block_message(
    message: Message,
    state: FSMContext
):
    if not is_admin(
        message.from_user.id
    ):
        await state.clear()
        return

    try:
        target_id = int(
            message.text.strip()
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
        await state.clear()
        return

    set_blocked(
        target_id,
        True
    )

    await message.answer(
        "🚫 Пользователь заблокирован.\n\n"
        "🔗 TOKEN сохранён.\n"
        "📦 Серверы сохранены.\n"
        "🗑 Ничего не удалялось."
    )

    await state.clear()


# ============================================================
# ADMIN UNBLOCK
# ============================================================

@dp.callback_query(
    F.data == "admin_unblock"
)
async def admin_unblock_start(
    callback: CallbackQuery,
    state: FSMContext
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    await state.set_state(
        AdminStates.unblock_user
    )

    await callback.message.edit_text(
        "🟢 РАЗБЛОКИРОВКА\n\n"
        "Отправь Telegram ID.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.message(
    AdminStates.unblock_user
)
async def admin_unblock_message(
    message: Message,
    state: FSMContext
):
    if not is_admin(
        message.from_user.id
    ):
        await state.clear()
        return

    try:
        target_id = int(
            message.text.strip()
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
        await state.clear()
        return

    set_blocked(
        target_id,
        False
    )

    user = get_user(
        target_id
    )

    try:
        if not check_subscription(
            user
        ):
            update_subscription(
                user
            )

        await message.answer(
            "🟢 Пользователь разблокирован.\n\n"
            "🔗 Постоянная ссылка сохранена.\n"
            "📦 10 ГБ.\n"
            "📅 Безлимитный срок."
        )

    except Exception as error:
        await message.answer(
            "🟢 Пользователь разблокирован,\n"
            "но возникла ошибка проверки:\n\n"
            + str(error)
        )

    await state.clear()


# ============================================================
# ERROR HANDLER
# ============================================================

@dp.errors()
async def errors_handler(
    event
):
    try:
        error = event.exception

        if (
            "message is not modified"
            in str(error).lower()
        ):
            return True

        print(
            "BOT ERROR:",
            repr(error)
        )

    except Exception:
        pass

    return True


# ============================================================
# MAIN
# ============================================================

async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не задан."
        )

    init_db()

    print(
        "🍑 Персик VPN Bot запущен."
    )

    print(
        "Схема: 1 пользователь = 1 TOKEN = 1 постоянная ссылка"
    )

    print(
        "Трафик: 10 ГБ"
    )

    print(
        "Срок: безлимит"
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":
    try:
        asyncio.run(
            main()
        )

    except KeyboardInterrupt:
        print(
            "Бот остановлен."
    )
