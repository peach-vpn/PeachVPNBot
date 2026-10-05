import base64
import json
import urllib.error
import urllib.request
import uuid

from config import (
    GITHUB_TOKEN,
    GITHUB_OWNER,
    GITHUB_REPO,
    GITHUB_BRANCH,
    SUBSCRIPTIONS_DIR,
)


def api_url(path):
    return (
        "https://api.github.com/repos/"
        + GITHUB_OWNER
        + "/"
        + GITHUB_REPO
        + "/contents/"
        + path
    )


def headers():
    return {
        "Authorization": "Bearer " + GITHUB_TOKEN,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "PeachVPNBot",
    }


def get_file(path):
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN не задан.")

    request = urllib.request.Request(
        api_url(path),
        headers=headers(),
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:
            return json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None

        body = error.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            "GitHub API "
            + str(error.code)
            + ": "
            + body
        )


def get_file_content(path):
    data = get_file(path)

    if not data:
        return None

    content = data.get("content", "")
    content = content.replace("\n", "")

    try:
        return base64.b64decode(
            content
        ).decode("utf-8")

    except Exception:
        return None


def put_file(path, content, message):
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN не задан.")

    old_file = get_file(path)

    payload = {
        "message": message,
        "content": base64.b64encode(
            content.encode("utf-8")
        ).decode("ascii"),
        "branch": GITHUB_BRANCH,
    }

    if old_file:
        sha = old_file.get("sha")

        if sha:
            payload["sha"] = sha

    data = json.dumps(
        payload
    ).encode("utf-8")

    request = urllib.request.Request(
        api_url(path),
        data=data,
        headers={
            **headers(),
            "Content-Type": "application/json",
        },
        method="PUT",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:
            return json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:
        body = error.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            "GitHub API "
            + str(error.code)
            + ": "
            + body
        )


def delete_file(path, message):
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN не задан.")

    old_file = get_file(path)

    if not old_file:
        return True

    sha = old_file.get("sha")

    if not sha:
        raise RuntimeError("Не найден SHA файла.")

    payload = {
        "message": message,
        "sha": sha,
        "branch": GITHUB_BRANCH,
    }

    data = json.dumps(
        payload
    ).encode("utf-8")

    request = urllib.request.Request(
        api_url(path),
        data=data,
        headers={
            **headers(),
            "Content-Type": "application/json",
        },
        method="DELETE",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ):
            return True

    except urllib.error.HTTPError as error:
        body = error.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            "GitHub API "
            + str(error.code)
            + ": "
            + body
        )


def raw_subscription_url(token):
    return (
        "https://raw.githubusercontent.com/"
        + GITHUB_OWNER
        + "/"
        + GITHUB_REPO
        + "/"
        + GITHUB_BRANCH
        + "/"
        + SUBSCRIPTIONS_DIR
        + "/"
        + token
        + ".txt"
    )


def subscription_path(token):
    return (
        SUBSCRIPTIONS_DIR
        + "/"
        + token
        + ".txt"
    )


# =========================================================
# ЗАГРУЗКА ВСЕХ СЕРВЕРОВ ИЗ nodes.txt
# =========================================================

def get_nodes():
    content = get_file_content("nodes.txt")

    if not content:
        raise RuntimeError(
            "GitHub не вернул nodes.txt."
        )

    nodes = []

    for raw_line in content.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if line.startswith("vless://"):
            nodes.append(line)
            continue

        if line.startswith("hysteria2://"):
            nodes.append(line)
            continue

        if line.startswith("hy2://"):
            nodes.append(line)
            continue

    if not nodes:
        raise RuntimeError(
            "В nodes.txt не найдено ни одного сервера."
        )

    return nodes


# =========================================================
# АКТИВНАЯ ПОДПИСКА
# =========================================================

def build_active_subscription(
    token,
    expires_at,
):
    nodes = get_nodes()

    lines = [
        'id="' + token[:6] + '"',
        "",
        "#profile-title: 🍑 Персик VPN",
        "",
        (
            "#announce: 🆓 Бесплатный VPN | "
            "🇳🇱 Нидерланды • 🇩🇪 Германия | "
            "⚡ VLESS + Hysteria2 | "
            "🔄 Серверы могут меняться "
            "и временно отключаться"
        ),
        "",
        (
            "#subscription-userinfo: "
            "upload=0; "
            "download=0; "
            "total=0; "
            "expire="
            + str(expires_at)
        ),
        "",
        "#profile-update-interval: 1",
        "",
    ]

    # ВАЖНО:
    # Добавляем ВСЕ найденные серверы.
    # Никаких [:1], [:4], [:5] и т.д.
    lines.extend(nodes)

    return "\n".join(lines) + "\n"


# =========================================================
# ПРОВЕРКА КОЛИЧЕСТВА СЕРВЕРОВ
# =========================================================

def get_nodes_count():
    return len(get_nodes())


# =========================================================
# СЛУЧАЙНЫЙ VLESS ДЛЯ ИСТЁКШЕЙ ПОДПИСКИ
# =========================================================

def random_vless():
    random_uuid = str(uuid.uuid4())

    random_host = (
        "node-"
        + uuid.uuid4().hex[:12]
        + ".invalid"
    )

    return (
        "vless://"
        + random_uuid
        + "@"
        + random_host
        + ":443"
        + "?type=tcp"
        + "&security=none"
        + "#"
    )


# =========================================================
# ИСТЁКШАЯ ПОДПИСКА
# =========================================================

def build_expired_subscription():
    return (
        "Подписка закончилась "
        "иди нахуй!\n\n"
        + random_vless()
        + "\n"
    )


# =========================================================
# ПУБЛИКАЦИЯ АКТИВНОЙ ПОДПИСКИ
# =========================================================

def publish_active(
    token,
    expires_at,
):
    content = build_active_subscription(
        token,
        expires_at,
    )

    put_file(
        subscription_path(token),
        content,
        "Update subscription "
        + token[:6]
        + " ("
        + str(get_nodes_count())
        + " nodes)",
    )

    return raw_subscription_url(token)


# =========================================================
# ПУБЛИКАЦИЯ ИСТЁКШЕЙ ПОДПИСКИ
# =========================================================

def publish_expired(token):
    put_file(
        subscription_path(token),
        build_expired_subscription(),
        "Expire subscription "
        + token[:6],
    )

    return raw_subscription_url(token)


# =========================================================
# УДАЛЕНИЕ ПОДПИСКИ
# =========================================================

def delete_subscription(token):
    return delete_file(
        subscription_path(token),
        "Delete subscription "
        + token[:6],
        )
