"""Nieuws ophalen via Alpaca en beoordelen: hoe positief/negatief is dit voor het aandeel?

Met ANTHROPIC_API_KEY in .env leest Claude het nieuws (veel slimmer, kost met Haiku bijna niks).
Zonder key wordt een simpele woordenlijst gebruikt.
"""
import json
import os
import re
from datetime import datetime

from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest

from data import API_KEY, SECRET_KEY

CLAUDE_MODEL = "claude-haiku-5-5"

_news = NewsClient(API_KEY, SECRET_KEY)


def fetch_news(symbol: str, since: datetime):
    """Nieuwe artikelen over `symbol` sinds `since`, oudste eerst."""
    req = NewsRequest(symbols=symbol, start=since, limit=50, sort="asc")
    return [a for a in _news.get_news(req).data["news"] if a.created_at > since]


# --- Simpele woordenlijst (fallback) ---
POSITIVE = {
    "beat": 2, "beats": 2, "tops": 2, "record": 1, "surge": 2, "soar": 2, "jumps": 1,
    "upgrade": 2, "upgraded": 2, "raises guidance": 3, "raises forecast": 3,
    "outperform": 1, "buy rating": 2, "partnership": 1, "deal": 1, "approval": 2,
    "strong demand": 2, "buyback": 2, "price target raised": 2,
}
NEGATIVE = {
    "miss": 2, "misses": 2, "plunge": 2, "falls": 1, "drops": 1, "downgrade": 2,
    "downgraded": 2, "cuts guidance": 3, "lowers forecast": 3, "lawsuit": 1,
    "probe": 2, "investigation": 2, "ban": 2, "export restrictions": 3, "tariff": 1,
    "recall": 2, "underperform": 1, "sell rating": 2, "price target cut": 2, "antitrust": 2,
}


def _keyword_score(text: str):
    t = text.lower()
    hits = {w: v for w, v in POSITIVE.items() if re.search(rf"\b{w}\b", t)}
    hits.update({w: -v for w, v in NEGATIVE.items() if re.search(rf"\b{w}\b", t)})
    total = sum(hits.values())
    return max(-1.0, min(1.0, total / 4)), ", ".join(hits) or "geen signaalwoorden"


# --- Claude ---
_claude = None
if os.getenv("ANTHROPIC_API_KEY"):
    import anthropic
    _claude = anthropic.Anthropic()

SYSTEM = """You are an equity news analyst. Rate how a news article is likely to move the \
given stock's price over the next few hours.
Score from -1 (strongly negative) to 1 (strongly positive).
Use 0 for articles that are irrelevant, opinion pieces, market recaps, or old news being repeated.
Reserve |score| >= 0.6 for genuinely new, material information (earnings, guidance, \
regulation, major deals, analyst rating changes from major firms)."""

SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "number"}, "reason": {"type": "string"}},
    "required": ["score", "reason"],
    "additionalProperties": False,
}


def _claude_score(symbol: str, article):
    resp = _claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": (
            f"Stock: {symbol}\nSource: {article.source}\nPublished: {article.created_at}\n"
            f"Headline: {article.headline}\nSummary: {article.summary or '-'}"
        )}],
    )
    if resp.stop_reason == "refusal":
        return 0.0, "geweigerd"
    text = next(b.text for b in resp.content if b.type == "text")
    out = json.loads(text)
    return max(-1.0, min(1.0, float(out["score"]))), out["reason"]


def score(symbol: str, article):
    """Geeft (score van -1 tot 1, uitleg)."""
    if _claude:
        try:
            return _claude_score(symbol, article)
        except Exception as e:
            print(f"  (Claude fout: {e}, val terug op woordenlijst)")
    return _keyword_score(f"{article.headline}. {article.summary or ''}")


USING = f"Claude ({CLAUDE_MODEL})" if _claude else "woordenlijst (zet ANTHROPIC_API_KEY in .env voor Claude)"
