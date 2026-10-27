from conftest import FakeResponse
from vie_alert.models import Offer
from vie_alert.notify import Telegram, chunk_lines, format_line, format_offer, to_plain


def sample(**kw):
    base = dict(source="Business France", uid="1", title="V.I.E <Treasury> & Cash", url="https://ex.com/o?a=1&b=2",
                company="A&B", city="Singapour", country="Singapour", published="2026-10-26", duration="12 mois",
                domain="Finance d'entreprise", basis="titre", description="x " * 300)
    base.update(kw)
    return Offer(**base)


def test_format_offer_contains_all_fields_and_escapes_html():
    text = format_offer(sample())
    assert "<b>V.I.E &lt;Treasury&gt; &amp; Cash</b>" in text
    assert "A&amp;B" in text and "Singapour, Singapour" in text and "26/10/2026" in text
    assert "Source : Business France" in text and "https://ex.com/o?a=1&amp;b=2" in text
    assert len(text) < 4096


def test_description_basis_is_flagged():
    assert "à vérifier" in format_offer(sample(basis="description"))


def test_chunks_respect_limit():
    lines = [format_line(sample(uid=str(i))) for i in range(200)]
    chunks = chunk_lines("En-tête", lines)
    assert len(chunks) > 1 and all(len(c) <= 3800 for c in chunks)
    assert sum(c.count("•") for c in chunks) == 200


def test_to_plain():
    assert to_plain('<b>x</b> <a href="https://e.com">lien</a> &amp;') == "x lien (https://e.com) &"


class SeqHttp:
    def __init__(self, responses):
        self.responses, self.payloads = list(responses), []

    def post(self, url, json=None, timeout=None):
        self.payloads.append(dict(json))
        return self.responses.pop(0)


def test_telegram_retries_429_and_falls_back_to_plain_text(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    tg = Telegram("123:abc", "42")
    tg.http = SeqHttp([
        FakeResponse(429, body={"ok": False, "parameters": {"retry_after": 1}}),
        FakeResponse(400, body={"ok": False, "description": "Bad Request: can't parse entities"}),
        FakeResponse(200, body={"ok": True}),
    ])
    assert tg.send("<b>Bonjour</b>", "https://ex.com")
    assert "parse_mode" not in tg.http.payloads[-1] and tg.http.payloads[-1]["text"] == "Bonjour"


def test_telegram_gives_up_on_bad_token(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    tg = Telegram("bad", "42")
    tg.http = SeqHttp([FakeResponse(401, body={"ok": False, "description": "Unauthorized"})])
    assert tg.send("x") is False
