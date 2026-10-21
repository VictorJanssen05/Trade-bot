"""Test de daytrade-strategieën uit intraday.py op minuutkoersen.

    python intraday_backtest.py                        -> NVDA AAPL AMD TSLA MSFT META, 6 maanden
    python intraday_backtest.py NVDA --maanden 12

Koersen worden bewaard in de map cache/, dus een tweede keer draaien gaat veel sneller.
"""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from data import get_minute_bars
from intraday import STRATEGIES, CLOSE_ALL_AT, Runner, minutes

COST = 0.0005  # 0.05% per aankoop en per verkoop (spread/slippage)
CACHE = Path(__file__).with_name("cache")


def load_bars(symbol, months):
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"{symbol}_{months}m_{datetime.now():%Y%m%d}.pkl"
    if f.exists():
        return pd.read_pickle(f)
    end = datetime.now(timezone.utc)
    bars = get_minute_bars(symbol, end - timedelta(days=30 * months), end)
    bars.index = bars.index.tz_convert("America/New_York")
    bars.to_pickle(f)
    return bars


def run(bars, strategy_cls):
    runner = Runner(strategy_cls())
    O, H, L, C, V = (bars[c].to_numpy() for c in ["open", "high", "low", "close", "volume"])
    T = bars.index
    rets, entry = [], None
    for i in range(len(bars)):
        b = SimpleNamespace(t=T[i], open=O[i], high=H[i], low=L[i], close=C[i], volume=V[i])
        action = runner.on_bar(b)
        if action is None:
            continue
        # Uitvoeren op de opening van de volgende minuut (zo snel kan de live-bot ook).
        same_day = i + 1 < len(bars) and T[i + 1].date() == T[i].date()
        price = O[i + 1] if same_day else C[i]
        if action == "buy" and same_day:
            entry, runner.in_pos = price, True
            runner.s.on_fill(price)
        elif action == "sell":
            rets.append(price / entry - 1 - 2 * COST)
            runner.in_pos = False
    r = np.array(rets)
    days = len(set(T.date))
    return {
        "rendement": float(np.prod(1 + r) - 1) if len(r) else 0.0,
        "trades": len(r),
        "per dag": len(r) / days,
        "winst%": float((r > 0).mean()) if len(r) else 0.0,
        "gem/trade": float(r.mean()) if len(r) else 0.0,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("aandelen", nargs="*", default=["NVDA", "AAPL", "AMD", "TSLA", "MSFT", "META"])
    p.add_argument("--maanden", type=int, default=6)
    args = p.parse_args()

    summary = {}
    for sym in [s.upper() for s in args.aandelen]:
        bars = load_bars(sym, args.maanden)
        hold = bars.close.iloc[-1] / bars.open.iloc[0] - 1
        rows = {name: run(bars, cls) for name, cls in STRATEGIES.items()}
        t = pd.DataFrame(rows).T
        print(f"\n=== {sym}  {bars.index[0]:%Y-%m-%d} t/m {bars.index[-1]:%Y-%m-%d}   "
              f"(kopen en vasthouden: {hold:+.1%})")
        print(fmt(t))
        summary[sym] = {"vasthouden": hold, **{n: r["rendement"] for n, r in rows.items()}}

    if len(summary) > 1:
        s = pd.DataFrame(summary).T
        s.loc["GEMIDDELD"] = s.mean()
        print("\n===== OVERZICHT rendement per strategie")
        print(s.map(lambda v: f"{v:+.1%}").to_string())


def fmt(t):
    t = t.copy()
    for c in ["rendement", "gem/trade"]:
        t[c] = t[c].map(lambda v: f"{v:+.2%}")
    t["winst%"] = t["winst%"].map(lambda v: f"{v:.0%}")
    t["per dag"] = t["per dag"].map(lambda v: f"{v:.1f}")
    t["trades"] = t["trades"].map(lambda v: f"{v:.0f}")
    return t.to_string()


if __name__ == "__main__":
    main()
