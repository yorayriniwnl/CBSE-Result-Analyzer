"""Guard the shared YOR visual contract across the Flask and Streamlit surfaces."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOKENS = json.loads((ROOT / "design" / "yor-tokens.json").read_text(encoding="utf-8"))
FLASK = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
STREAMLIT = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")

palette = TOKENS["palette"]
required_colors = [*palette.values(), TOKENS["gradient"]]
sources = {"templates/index.html": FLASK, "streamlit_app.py": STREAMLIT}
missing = [
    f"{color} in {name}"
    for name, source in sources.items()
    for color in required_colors
    if color.lower() not in source.lower()
]
missing.extend(
    f"{state} in README.md"
    for state in TOKENS["evidenceStates"]
    if state not in README
)
if missing:
    raise SystemExit("YOR design contract failed:\n- " + "\n- ".join(missing))

print("YOR design contract: PASS")
