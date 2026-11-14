import re
import socket

MAX_LEN = 39  # GitHub's username limit
FALLBACK = "local-user"


def sanitize_owner(raw: str) -> str:
    """Turn an OS hostname into a valid id prefix: lowercase letters, digits and hyphens only.

    No underscores (they separate owner from family name), and no domain suffix like ".local".
    """
    first_label = raw.strip().lower().split(".")[0]
    cleaned = re.sub(r"[^a-z0-9]+", "-", first_label).strip("-")[:MAX_LEN].strip("-")
    return cleaned or FALLBACK


def read_hostname_owner() -> str:
    try:
        return sanitize_owner(socket.gethostname())
    except OSError:
        return FALLBACK
