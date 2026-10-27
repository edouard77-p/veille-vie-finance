"""La voie rapide (Code.gs) est exécutée dans Node avec des services Google simulés."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from vie_alert.classify import KEYWORDS_FILE

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "apps_script_harness.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js absent")


def node(mode: str, stdin: str = "") -> dict | list:
    r = subprocess.run(["node", str(HARNESS), mode], input=stdin, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_embedded_keywords_match_config():
    import re
    code = (ROOT / "apps_script" / "Code.gs").read_text(encoding="utf-8")
    block = re.search(r"// <KEYWORDS>\nvar DEFAULT_KEYWORDS = (.*?);\n// </KEYWORDS>", code, re.S).group(1)
    expected = json.loads(KEYWORDS_FILE.read_text(encoding="utf-8"))
    expected.pop("_lisez_moi", None)
    assert json.loads(block) == expected, "Lance : python tools/sync_keywords.py"


def test_js_and_python_classifiers_agree(clf, cases):
    inputs = [[t, "", ""] for t, _ in cases["finance"]] + [[t, "", ""] for t in cases["not_finance"]]
    inputs += [[t, d, ""] for t, d, _ in cases["description_cases"]]
    inputs += [[t, "", ""] for t in cases["vie_yes"] + cases["vie_no"]]
    inputs += [["VIE Chargé de mission", "", "Finance / Comptabilité"], ["Contrôleur Crédit – Trade Finance", "", ""]]
    js = node("parity", json.dumps(inputs))
    for (title, desc, tags), j in zip(inputs, js):
        v = clf.classify(title, desc, tags)
        assert j["isFinance"] == v.is_finance, title
        assert j["domain"] == v.domain and j["basis"] == v.basis, (title, j, v)
        assert j["vie"] == clf.looks_vie(title, desc), title


def test_fastlane_scenario():
    out = node("scenario")
    assert out["chatId"] == "4242"
    assert out["afterInstall"] == {**out["afterInstall"], "telegram": 1, "triggers": 1, "sentIds": 15, "seenIds": 150}
    assert len(out["afterNew"]) == 1 and "Treasury Analyst" in out["afterNew"][0]["text"] and out["afterNew"][0]["button"]
    assert out["repeat"] == 0
    assert out["doGet"] == {"ok": True, "hasNew": True, "bfOk": True, "badOk": False}
    assert out["failureAlerts"] == 1 and out["recovered"]
    assert len(out["gmail"]["messages"]) == 1 and out["gmail"]["labelled"] == ["vie-relaye"]
    msg = out["gmail"]["messages"][0]
    assert msg.count("•") == 3 and "https://ex.com/job" in msg and "Aide comptable" in msg and "désabonner" not in msg
    assert out["ghWatchAlert"]
