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
                response.read().decode()
            )

    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None

        raise


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

    if old_file and old_file.get("sha"):
        payload["sha"] = old_file["sha"]

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

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:
        return json.loads(
            response.read().decode()
        )


def delete_file(
    path,
    message
):
    if not GITHUB_TOKEN:
        raise RuntimeError(
            "GITHUB_TOKEN не задан"
        )

    old_file = get_file(path)

    if not old_file:
        return False

    payload = {
        "message": message,
        "sha": old_file["sha"],
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
            "Content-Type":
                "application/json"
        },
        method="DELETE"
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:
        return True


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
