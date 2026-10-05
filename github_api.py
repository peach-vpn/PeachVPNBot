import base64
import json
import urllib.error
import urllib.request

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
        raise RuntimeError(
            "GITHUB_TOKEN не задан"
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


def put_file(
    path,
    content,
    message
):
    if not GITHUB_TOKEN:
        raise RuntimeError(
            "GITHUB_TOKEN не задан"
        )

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
