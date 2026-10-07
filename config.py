import os


BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    ""
)

ADMIN_ID = int(
    os.getenv(
        "ADMIN_ID",
        "0"
    )
)

DATABASE_FILE = os.getenv(
    "DATABASE_FILE",
    "/data/peachvpn.db"
)

GITHUB_TOKEN = os.getenv(
    "GITHUB_TOKEN",
    ""
)

GITHUB_OWNER = os.getenv(
    "GITHUB_OWNER",
    "peach-vpn"
)

GITHUB_REPO = os.getenv(
    "GITHUB_REPO",
    "Free-VPN-"
)

GITHUB_BRANCH = os.getenv(
    "GITHUB_BRANCH",
    "main"
)

SUBSCRIPTIONS_DIR = "subscriptions"

NODES_FILE = "nodes.txt"

PRO_FILE = "pro.txt"

FREE_DAYS = 30

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не задан"
    )

if not ADMIN_ID:
    raise RuntimeError(
        "ADMIN_ID не задан"
    )

if not GITHUB_TOKEN:
    raise RuntimeError(
        "GITHUB_TOKEN не задан"
    )
