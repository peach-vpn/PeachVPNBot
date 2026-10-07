import os


BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    ""
)

ADMIN_ID = int(
    os.getenv(
        "ADMIN_ID",
        "8847877937"
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
