"""Dessins à la demande (propositions graphiques) via OpenRouter.

Lit .state/image-request.json : {"name": "...", "items": [{"file": "a.png", "prompt": "...",
"aspect_ratio": "1:1", "refs": ["knowledge-hub/comics/kit/assets/characters/duo-reference-v2.png"]}]}
Les refs sont des chemins du dépôt du site. Sortie dans OUTPUT (publié sur la branche ecoute).
Usage : python scripts/draw-request.py SITE OUTPUT
"""
import importlib.util
import json
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("weekly", Path(__file__).parent / "iastro-weekly.py")
weekly = importlib.util.module_from_spec(spec); spec.loader.exec_module(weekly)

site, out = Path(sys.argv[1]), Path(sys.argv[2])
request = json.loads(Path(".state/image-request.json").read_text())
out.mkdir(parents=True, exist_ok=True)
for item in request["items"]:
    refs = [site / r for r in item.get("refs", [])]
    weekly.draw(item["prompt"], refs, item.get("aspect_ratio", "1:1"), out / item["file"])
(out / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2))
print(f"Coût total : {sum(weekly.COSTS):.2f} $")
