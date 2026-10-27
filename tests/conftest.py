import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vie_alert.classify import Classifier  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


class FakeResponse:
    def __init__(self, status=200, body=None, text=None, content=None):
        self.status_code = status
        self._body = body
        self.text = text if text is not None else (json.dumps(body) if body is not None else "")
        self.content = content if content is not None else self.text.encode()
        self.ok = 200 <= status < 300

    def json(self):
        if self._body is None:
            return json.loads(self.text)
        return self._body


class FakeSession:
    """Session HTTP factice : route(method, url, kwargs) -> FakeResponse."""

    def __init__(self, route):
        self.route = route
        self.calls = []
        self.headers = {}

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return self.route(method, url, kw)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)


@pytest.fixture
def clf():
    return Classifier.from_file()


@pytest.fixture
def cases():
    return json.loads((FIXTURES / "classification_cases.json").read_text(encoding="utf-8"))


def bf_raw(i, title="VIE Financial Analyst", **extra):
    raw = {"id": i, "missionTitle": title, "organizationName": f"Société {i}", "cityName": "SINGAPOUR",
           "countryName": "SINGAPOUR", "missionDuration": 12, "indemnite": 3214.5,
           "startBroadcastDate": "2026-10-26T08:00:00Z", "missionStartDate": "2027-01-01T00:00:00",
           "endBroadcastDate": "2026-11-25T00:00:00", "missionDescription": "<p>Analyse <b>financière</b> et reporting.</p>",
           "missionProfile": "Bac+5 finance", "missionType": "VIE"}
    raw.update(extra)
    return raw
