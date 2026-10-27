"""Recopie config/keywords.json dans apps_script/Code.gs (copie de secours intégrée).

À lancer après avoir modifié les mots-clés si tu n'utilises pas KEYWORDS_URL :
    python tools/sync_keywords.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KW = ROOT / "config" / "keywords.json"
GS = ROOT / "apps_script" / "Code.gs"
BLOCK = re.compile(r"(// <KEYWORDS>\n).*?(\n// </KEYWORDS>)", re.S)


def _compact(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def render() -> str:
    """Une ligne par liste de motifs : plus court à coller dans l'éditeur Apps Script."""
    data = json.loads(KW.read_text(encoding="utf-8"))
    data.pop("_lisez_moi", None)
    out = ["var DEFAULT_KEYWORDS = {"]
    items = list(data.items())
    for i, (key, value) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        if isinstance(value, dict):
            out.append(f"  {_compact(key)}: {{")
            sub = list(value.items())
            for j, (k, v) in enumerate(sub):
                out.append(f"    {_compact(k)}: {_compact(v)}" + ("," if j < len(sub) - 1 else ""))
            out.append("  }" + comma)
        else:
            out.append(f"  {_compact(key)}: {_compact(value)}{comma}")
    out.append("};")
    return "\n".join(out)


def main() -> int:
    code = GS.read_text(encoding="utf-8")
    if not BLOCK.search(code):
        print("Marqueurs <KEYWORDS> introuvables dans Code.gs")
        return 1
    GS.write_text(BLOCK.sub(lambda m: m.group(1) + render() + m.group(2), code), encoding="utf-8")
    print("Code.gs mis à jour avec config/keywords.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
