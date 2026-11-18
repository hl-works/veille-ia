import os
import tempfile

# Les tests ne doivent jamais écrire dans journal/ du dépôt (données publiées).
os.environ.setdefault("JOURNAL_DIR", tempfile.mkdtemp(prefix="journal-tests-"))


import pytest


@pytest.fixture(autouse=True)
def _canal_a_l_heure(request, monkeypatch):
    """Les tests d'envoi simulent un run du matin : jamais « en retard » sauf test dédié."""
    if "canal_retard" not in request.node.name:
        monkeypatch.setattr("veille.audio.canal_trop_tard", lambda *a, **k: False, raising=False)
