import os
import tempfile

# Les tests ne doivent jamais écrire dans journal/ du dépôt (données publiées).
os.environ.setdefault("JOURNAL_DIR", tempfile.mkdtemp(prefix="journal-tests-"))
