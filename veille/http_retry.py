"""POST HTTP avec relances quand l'API est saturée (429) ou en erreur serveur (5xx)."""
from __future__ import annotations

import time

import requests


def post(url: str, *, attempts: int = 5, **kw) -> requests.Response:
    """Attente 10 s, 20 s, 40 s, 60 s entre essais. Les autres réponses sont rendues telles quelles."""
    for i in range(attempts):
        try:
            r = requests.post(url, **kw)
        except requests.RequestException:
            if i == attempts - 1:
                raise
        else:
            if r.status_code != 429 and r.status_code < 500:
                return r
            if i == attempts - 1:
                return r
        time.sleep(min(60, 10 * 2 ** i))
    return r
