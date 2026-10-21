"""Test de nieuwsstrategie op nieuws en minuutkoersen uit het verleden.

    python news_backtest.py                 -> 6 maanden, woordenlijst (gratis)
    python news_backtest.py --claude        -> laat Claude het oude nieuws beoordelen (kost geld, zie schatting)
    python news_backtest.py --maanden 12
    python news_backtest.py AAPL AMD TSLA   -> andere aandelen

Werkwijze: de eerste 2/3 van de periode wordt gebruikt om de beste instellingen te zoeken,
de laatste 1/3 om te kijken of die instellingen ook werken op data die de zoektocht niet heeft gezien.
Scores worden opgeslagen in news_scores.json, dus Claude hoeft elk artikel maar één keer te lezen.
"""
import argparse
import itertools
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import news
import news_bot as cfg
from data import get_daily_bars, get_minute_bars
from strategies import trend_200

COST = 0.0005            # 0.05% per trade voor spread/slippage
REACTION_SEC = 30        # zo snel reageert de bot op een nieuw artikel
GRID = {
    "buy": [0.2, 0.4, 0.6, 0.8],
    "tp": [0.01, 0.02, 0.04, 0.08],
    "sl": [0.01, 0.02, 0.04],
}
CACHE = Path(__file__).with_name("news_scores.json")


def load_scores(symbol, articles, use_claude):
    key = f"{symbol}:{news.CLAUDE_MODEL if use_claude else 'woorden'}"
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    cache.setdefault(key, {})
    todo = [a for a in articles if str(a.id) not in cache[key]]

    if use_claude and todo:
        print(f"Claude beoordeelt {len(todo)} artikelen (geschat ~${len(todo) * 0.0002:.2f}, "
              f"duurt een paar minuten)...")
    score_fn = (lambda a: news.score(symbol, a)[0]) if use_claude else \
        (lambda a: news._keyword_score(f"{a.headline}. {a.summary or ''}")[0])

    with ThreadPoolExecutor(max_workers=8 if use_claude else 1) as pool:
        for n, (a, s) in enumerate(zip(todo, pool.map(score_fn, todo)), 1):
            cache[key][str(a.id)] = s
            if use_claude and n % 200 == 0:
                print(f"  {n}/{len(todo)}")
                CACHE.write_text(json.dumps(cache))
    CACHE.write_text(json.dumps(cache))
    return [cache[key][str(a.id)] for a in articles]


def build_events(articles, scores, bars, daily):
    """Koppel elk artikel aan de minuut waarop de bot erop zou handelen."""
    times = bars.index.values
    trend = trend_200(daily).shift(1)  # trend volgens het slot van de vorige dag
    trend.index = trend.index.tz_convert("America/New_York").date
    ev = []
    for a, s in zip(articles, scores):
        t = np.datetime64(a.created_at.astimezone(timezone.utc).replace(tzinfo=None) +
                          timedelta(seconds=REACTION_SEC), "ns")
        i = int(np.searchsorted(times, t))
        if i >= len(times):
            continue
        bar_time = bars.index[i]
        if bar_time - a.created_at > timedelta(minutes=cfg.MAX_NEWS_AGE_MIN):
            continue  # nieuws buiten beurstijd: is al oud als de beurs opent
        up = trend.get(bar_time.tz_convert("America/New_York").date(), 0)
        ev.append((i, s, bool(up == 1)))
    return ev


def exit_scan(O, H, L, entry, tp, sl, a, b):
    """Eerste bar in [a, b) waar winst- of stop-order geraakt wordt."""
    if a >= b:
        return None
    stop, target = entry * (1 - sl), entry * (1 + tp)
    hit = (L[a:b] <= stop) | (H[a:b] >= target)
    if not hit.any():
        return None
    i = a + int(hit.argmax())
    if L[i] <= stop:  # als allebei in dezelfde minuut: neem voorzichtig het verlies
        return i, min(O[i], stop)
    return i, max(O[i], target)


def simulate(events, O, H, L, C, T, buy, sell, tp, sl, start, end):
    rets, pos, last_trade = [], None, None
    cooldown = np.timedelta64(cfg.COOLDOWN_MIN, "m")

    def close(price):
        rets.append(price / pos[0] - 1 - 2 * COST)

    for i, s, up in events:
        if i < start or i >= end:
            continue
        if pos:
            ex = exit_scan(O, H, L, pos[0], tp, sl, pos[1], i)
            if ex:
                close(ex[1]); pos = None
            else:
                pos = (pos[0], i)
        if pos and s <= sell:
            close(O[i]); pos, last_trade = None, T[i]
        elif not pos and s >= buy and up and (last_trade is None or T[i] - last_trade >= cooldown):
            pos, last_trade = (O[i], i), T[i]
    if pos:
        ex = exit_scan(O, H, L, pos[0], tp, sl, pos[1], end)
        close(ex[1] if ex else C[end - 1])

    r = np.array(rets)
    return {
        "rendement": float(np.prod(1 + r) - 1) if len(r) else 0.0,
        "trades": len(r),
        "winst%": float((r > 0).mean()) if len(r) else 0.0,
        "gem/trade": float(r.mean()) if len(r) else 0.0,
    }


def backtest(symbol, months, use_claude):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30 * months)
    print(f"\n##### {symbol}: nieuws en minuutkoersen ophalen ({months} maanden)...")
    articles = news.fetch_all_news(symbol, start, end)
    bars = get_minute_bars(symbol, start, end)
    daily = get_daily_bars(symbol, days=30 * months + 400)
    print(f"{len(articles)} artikelen, {len(bars)} minuten")

    scores = load_scores(symbol, articles, use_claude)
    events = build_events(articles, scores, bars, daily)
    O, H, L, C = (bars[c].to_numpy() for c in ["open", "high", "low", "close"])
    T = bars.index.values
    split = len(bars) * 2 // 3

    def run(buy, tp, sl, a, b):
        return simulate(events, O, H, L, C, T, buy, -buy, tp, sl, a, b)

    rows = []
    for buy, tp, sl in itertools.product(GRID["buy"], GRID["tp"], GRID["sl"]):
        r = run(buy, tp, sl, 0, split)
        if r["trades"] >= 5:
            rows.append({"grens": buy, "winst bij": tp, "stop": sl, **r})
    if not rows:
        print("Te weinig trades om iets te zeggen.")
        return None
    train = pd.DataFrame(rows).sort_values("rendement", ascending=False)

    period = lambda a, b: f"{bars.index[a]:%Y-%m-%d} t/m {bars.index[b - 1]:%Y-%m-%d}"
    hold = lambda a, b: C[b - 1] / O[a] - 1
    print(f"\n=== {symbol} ZOEKPERIODE {period(0, split)}   (kopen en vasthouden: {hold(0, split):+.1%})")
    print("Top 5 instellingen:")
    print(fmt(train.head(5)))

    print(f"\n=== {symbol} TESTPERIODE {period(split, len(bars))}   "
          f"(kopen en vasthouden: {hold(split, len(bars)):+.1%})")
    best = train.iloc[0]
    tests = {
        "beste uit zoekperiode": (best["grens"], best["winst bij"], best["stop"]),
        "huidige bot": (cfg.BUY_SCORE, cfg.TAKE_PROFIT, cfg.STOP_LOSS),
    }
    out = pd.DataFrame([{"": name, "grens": b, "winst bij": t, "stop": s, **run(b, t, s, split, len(bars))}
                        for name, (b, t, s) in tests.items()]).set_index("")
    out.index.name = None
    print(fmt(out))
    return {
        "aandeel": symbol,
        "vasthouden": hold(split, len(bars)),
        "huidige bot": out.loc["huidige bot", "rendement"],
        "trades": out.loc["huidige bot", "trades"],
        "beste": out.loc["beste uit zoekperiode", "rendement"],
        "beste instelling": f"{best['grens']}/{best['winst bij']:.0%}/{best['stop']:.0%}",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("aandelen", nargs="*", default=[cfg.SYMBOL])
    p.add_argument("--maanden", type=int, default=6)
    p.add_argument("--claude", action="store_true")
    args = p.parse_args()

    results = [r for sym in args.aandelen if (r := backtest(sym.upper(), args.maanden, args.claude))]
    if len(results) > 1:
        t = pd.DataFrame(results).set_index("aandeel")
        t.index.name = None
        print("\n===== OVERZICHT TESTPERIODES (beste instelling = grens/winst bij/stop)")
        for c in ["vasthouden", "huidige bot", "beste"]:
            t[c] = t[c].map(lambda v: f"{v:+.1%}")
        print(t.to_string())
    print("\nWerkt 'beste uit zoekperiode' ook goed in de testperiode? Dan is het waarschijnlijk geen toeval.")


def fmt(t):
    t = t.copy()
    for c in ["rendement", "gem/trade"]:
        t[c] = t[c].map(lambda v: f"{v:+.2%}")
    t["winst%"] = t["winst%"].map(lambda v: f"{v:.0%}")
    for c in ["winst bij", "stop"]:
        t[c] = t[c].map(lambda v: f"{v:.0%}")
    return t.to_string(index=not isinstance(t.index, pd.RangeIndex))


if __name__ == "__main__":
    main()
