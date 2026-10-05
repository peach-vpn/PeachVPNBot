import base64
import json
import urllib.error
import urllib.request

from config import (
    GITHUB_TOKEN,
    GITHUB_OWNER,
    GITHUB_REPO,
    GITHUB_BRANCH,
    SUBSCRIPTIONS_DIR
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
        "Authorization": "Bearer "
        + GITHUB_TOKEN,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version":
            "2022-11-28",
        "User-Agent":
            "PeachVPNBot"
    }


def get_file(path):
    if not GITHUB_TOKEN:
        raise RuntimeError(
            "GITHUB_TOKEN не задан."
        )

    request = urllib.request.Request(
        api_url(path),
        headers=headers()
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:
            return json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None

        body = error.read().decode(
            "utf-8",
            errors="replace"
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

    content = data.get(
        "content",
        ""
    )

    content = content.replace(
        "\n",
        ""
    )

    try:
        return base64.b64decode(
            content
        ).decode("utf-8")
    except Exception:
        return None


def put_file(
    path,
    content,
    message
):
    if not GITHUB_TOKEN:
        raise RuntimeError(
            "GITHUB_TOKEN не задан."
        )

    old_file = get_file(path)

    payload = {
        "message": message,
        "content": base64.b64encode(
            content.encode("utf-8")
        ).decode("ascii"),
        "branch": GITHUB_BRANCH
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
            "Content-Type":
                "application/json"
        },
        method="PUT"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:
            return json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except urllib.error.HTTPError as error:
        body = error.read().decode(
            "utf-8",
            errors="replace"
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


def get_nodes():
    content = get_file_content(
        "nodes.txt"
    )

    if not content:
        return []

    nodes = []

    for line in content.splitlines():
        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if line.startswith(
            "vless://"
        ):
            nodes.append(line)

        elif line.startswith(
            "hysteria2://"
        ):
            nodes.append(line)

        elif line.startswith(
            "hy2://"
        ):
            nodes.append(line)

    return nodes


def build_subscription(
    token,
    expires_at
):
    nodes = get_nodes()

    if not nodes:
        raise RuntimeError(
            "В nodes.txt нет серверов."
        )

    # Используем максимум первые 4 сервера.
    nodes = nodes[:4]

    lines = [
        'id="' + token[:6] + '"',
        "#profile-title: 🍑 Персик VPN",
        (
            "#announce: 🆓 Бесплатный VPN | "
            "🇳🇱 Нидерланды • "
            "🇩🇪 Германия • "
            "🇰🇿 Казахстан | "
            "⚡ VLESS + Hysteria2"
        ),
        (
            "#subscription-userinfo: "
            "upload=0; "
            "download=0; "
            "total=0; "
            "expire="
            + str(expires_at)
        ),
        "#profile-update-interval: 1",
        ""
    ]

    lines.extend(nodes)

    return "\n".join(lines) + "\n"


def publish_subscription(
    token,
    expires_at
):
    content = build_subscription(
        token,
        expires_at
    )

    path = subscription_path(
        token
    )

    put_file(
        path,
        content,
        "Update subscription "
        + token[:6]
    )

    return raw_subscription_url(
        token
        )
