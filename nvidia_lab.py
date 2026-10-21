"""Test heel veel taktieken op één aandeel (standaard Nvidia).

    python nvidia_lab.py          -> Nvidia
    python nvidia_lab.py AMD      -> ander aandeel

Een taktiek "wint" als hij in de eerste 4 jaar EN in de laatste 4 jaar meer verdiende
dan zelf vasthouden. Daarna doen we hetzelfde op door elkaar geschudde koersen
(dezelfde dagelijkse stappen, maar in willekeurige volgorde). Daar kan geen taktiek
echt werken, dus zie je hoeveel winnaars je door puur geluk krijgt.
"""
import sys

import numpy as np
import pandas as pd

from backtest import stats
from data import get_daily_bars
from strategies import _hold, breakout, rsi, sma

SCHUD_KEREN = 20


# ---------- taktieken met instelbare getallen ----------

def trend(n, buffer=0.0):
    def f(df):
        line = sma(df.close, n).to_numpy()
        c = df.close.to_numpy()
        return _hold(df, c > line * (1 + buffer), c < line * (1 - buffer))
    return f


def sma_x(fast, slow):
    return lambda df: (sma(df.close, fast) > sma(df.close, slow)).astype(int)


def ema_x(fast, slow):
    return lambda df: (df.close.ewm(span=fast).mean() > df.close.ewm(span=slow).mean()).astype(int)


def macd_x(fast, slow, sig):
    def f(df):
        line = df.close.ewm(span=fast).mean() - df.close.ewm(span=slow).mean()
        return (line > line.ewm(span=sig).mean()).astype(int)
    return f


def momentum(days):
    return lambda df: (df.close > df.close.shift(days)).astype(int)


def dip(entry, exit_n, trend_n=200):
    def f(df):
        buy = ((df.close > sma(df.close, trend_n)) & (rsi(df.close, 2) < entry)).to_numpy()
        return _hold(df, buy, (df.close > sma(df.close, exit_n)).to_numpy())
    return f


def bollinger_x(n, k):
    def f(df):
        mid = sma(df.close, n)
        buy = ((df.close < mid - k * df.close.rolling(n).std()) & (df.close > sma(df.close, 200))).to_numpy()
        return _hold(df, buy, (df.close > mid).to_numpy())
    return f


def trend_dip(entry, trend_n):
    def f(df):
        up = (df.close > sma(df.close, trend_n)).to_numpy()
        return _hold(df, up & (rsi(df.close, 2) < entry).to_numpy(), ~up)
    return f


def taktieken():
    t = {}
    for n in [10, 20, 30, 50, 75, 100, 150, 200, 250]:
        t[f"trend {n}d"] = trend(n)
    for n in [50, 100, 200]:
        for b in [0.02, 0.05, 0.10]:
            t[f"trend {n}d met {b:.0%} speling"] = trend(n, b)
    for f_, s_ in [(5, 20), (10, 30), (10, 50), (20, 50), (20, 100), (50, 100), (50, 200), (100, 200)]:
        t[f"gemiddelden {f_}/{s_}d"] = sma_x(f_, s_)
        t[f"ema {f_}/{s_}d"] = ema_x(f_, s_)
    for e in [10, 20, 55, 100]:
        for x in [5, 10, 20, 50]:
            if x < e:
                t[f"breakout {e}/{x}d"] = (lambda e, x: lambda df: breakout(df, e, x))(e, x)
    for e in [5, 10, 20, 30]:
        for x in [3, 5, 10]:
            t[f"dip kopen rsi<{e}, uit na {x}d"] = dip(e, x)
    for m in [(12, 26, 9), (8, 21, 5), (5, 35, 5), (19, 39, 9)]:
        t[f"macd {m[0]}/{m[1]}/{m[2]}"] = macd_x(*m)
    for d in [21, 63, 126, 252]:
        t[f"momentum {d}d"] = momentum(d)
    for n in [10, 20, 50]:
        for k in [1.5, 2.0, 2.5]:
            t[f"bollinger {n}d {k}x"] = bollinger_x(n, k)
    for e in [10, 20, 30]:
        for n in [50, 100, 200]:
            t[f"trend {n}d + instap na dip rsi<{e}"] = trend_dip(e, n)
    return t


# ---------- testen ----------

def test_alles(df, tak):
    helft = len(df) // 2
    delen = [slice(0, helft), slice(helft, len(df))]
    hold = pd.Series(1, index=df.index)
    zelf = [stats(df.iloc[d], hold.iloc[d])["per jaar"] for d in delen]
    recent = slice(len(df) - 2 * 252, len(df))
    rijen = []
    for naam, f in tak.items():
        pos = f(df)
        heel = stats(df, pos)
        stukken = [stats(df.iloc[d], pos.iloc[d])["per jaar"] for d in delen]
        rijen.append({"taktiek": naam, "per jaar": heel["per jaar"], "ergste daling": heel["max daling"],
                      "eerste 4 jaar": stukken[0], "laatste 4 jaar": stukken[1],
                      "laatste 2 jaar": stats(df.iloc[recent], pos.iloc[recent])["per jaar"],
                      "wint": stukken[0] > zelf[0] and stukken[1] > zelf[1]})
    return pd.DataFrame(rijen), zelf


def geschud(df, rng):
    """Zelfde dagelijkse stappen als het echte aandeel, maar in willekeurige volgorde."""
    r = np.log(df.close).diff().fillna(0).to_numpy()
    hi, lo = (df.high / df.close).to_numpy(), (df.low / df.close).to_numpy()
    idx = rng.permutation(len(r))
    c = df.close.iloc[0] * np.exp(np.cumsum(r[idx]))
    return pd.DataFrame({"open": c, "high": c * hi[idx], "low": c * lo[idx], "close": c}, index=df.index)


def main():
    sym = (sys.argv[1] if len(sys.argv) > 1 else "NVDA").upper()
    df = get_daily_bars(sym, days=int(8 * 365.25))
    tak = taktieken()
    print(f"{len(tak)} taktieken testen op {sym} ({df.index[0]:%Y} t/m {df.index[-1]:%Y})...")
    t, zelf = test_alles(df, tak)
    hold = pd.Series(1, index=df.index)
    zelf_heel = stats(df, hold)
    zelf_2j = stats(df.iloc[-2 * 252:], hold.iloc[-2 * 252:])

    rng = np.random.default_rng(42)
    geluk = []
    for i in range(SCHUD_KEREN):
        g, _ = test_alles(geschud(df, rng), tak)
        geluk.append(int(g.wint.sum()))
        print(f"  toets op geschudde koersen {i + 1}/{SCHUD_KEREN}", end="\r")

    print(f"\n\nZelf vasthouden: {zelf_heel['per jaar']:+.0%} per jaar, ergste daling {zelf_heel['max daling']:+.0%}"
          f"  (eerste 4 jaar {zelf[0]:+.0%}, laatste 4 jaar {zelf[1]:+.0%}, laatste 2 jaar {zelf_2j['per jaar']:+.0%})")
    print(f"\n{int(t.wint.sum())} van de {len(t)} taktieken verdienden in BEIDE periodes meer dan vasthouden.")
    print(f"Bij geschudde koersen (puur geluk) waren dat er gemiddeld {np.mean(geluk):.0f} "
          f"(tussen {min(geluk)} en {max(geluk)}).")
    if t.wint.sum() <= max(geluk):
        print("-> Dat is niet meer dan geluk. Geen enkele taktiek is echt beter dan vasthouden.")
    else:
        print("-> Dat is meer dan geluk: hier lijkt echt iets te zitten.")

    top = t.sort_values("per jaar", ascending=False).head(15).set_index("taktiek")
    top.index.name = None
    top["wint"] = top["wint"].map({True: "ja", False: "nee"})
    top = top.rename(columns={"wint": "wint in beide"})
    for c in ["per jaar", "ergste daling", "eerste 4 jaar", "laatste 4 jaar", "laatste 2 jaar"]:
        top[c] = top[c].map(lambda v: f"{v:+.0%}")
    print("\nDe 15 taktieken met de meeste winst per jaar:\n")
    print(top.to_string())


if __name__ == "__main__":
    main()
