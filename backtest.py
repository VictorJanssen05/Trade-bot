"""Test alle strategieën op historische data.

    python backtest.py              -> Nvidia, 8 jaar
    python backtest.py AAPL TSLA    -> andere aandelen
"""
import sys

import pandas as pd

from data import get_daily_bars
from strategies import STRATEGIES

SYMBOLS = sys.argv[1:] or ["NVDA"]
YEARS = 8
COST = 0.0005  # 0.05% per trade voor spread/slippage


def run(df, strategy):
    pos = strategy(df)
    ret = df.close.pct_change().fillna(0)
    trades = pos.diff().abs().fillna(pos.iloc[0])
    # Signaal op slot van dag X -> rendement vanaf dag X+1.
    daily = pos.shift(1).fillna(0) * ret - trades * COST
    equity = (1 + daily).cumprod()
    years = len(df) / 252
    return {
        "rendement": equity.iloc[-1] - 1,
        "per jaar": equity.iloc[-1] ** (1 / years) - 1,
        "max daling": (equity / equity.cummax() - 1).min(),
        "trades": int(trades.sum() // 2),
        "in markt": pos.mean(),
    }


def main():
    all_rows = []
    for sym in SYMBOLS:
        df = get_daily_bars(sym, days=int(YEARS * 365.25))
        print(f"\n=== {sym}  ({df.index[0]:%Y-%m-%d} t/m {df.index[-1]:%Y-%m-%d})")
        rows = {name: run(df, fn) for name, fn in STRATEGIES.items()}
        table = pd.DataFrame(rows).T
        print(fmt(table))
        all_rows.append(table.assign(symbol=sym))

    if len(SYMBOLS) == 1:
        return
    avg = pd.concat(all_rows).drop(columns="symbol").groupby(level=0).mean()
    print("\n=== GEMIDDELD over alle aandelen (gesorteerd op beste verhouding rendement/daling)")
    avg["score"] = avg["per jaar"] / -avg["max daling"]
    print(fmt(avg.sort_values("score", ascending=False)))


def fmt(t):
    t = t.copy()
    for c in ["rendement", "per jaar", "max daling", "in markt"]:
        t[c] = t[c].map(lambda v: f"{v:+.0%}" if c != "in markt" else f"{v:.0%}")
    if "score" in t:
        t["score"] = t["score"].map(lambda v: f"{v:.2f}")
    t["trades"] = t["trades"].map(lambda v: f"{v:.0f}")
    return t.to_string()


if __name__ == "__main__":
    main()
