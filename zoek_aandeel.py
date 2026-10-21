"""Zoekt aandelen waar de trend-taktiek (trend_200) goed werkte.

    python zoek_aandeel.py

De taktiek: alleen in het aandeel zitten als de koers boven het gemiddelde van de
laatste 200 dagen staat. Zakt hij eronder, dan verkopen.

Om geluk uit te sluiten testen we de afgelopen 8 jaar in twee stukken van 4 jaar.
Alleen als de taktiek in BEIDE stukken goed werkte, telt het.
"""
import pandas as pd

from backtest import run
from data import get_daily_bars
from strategies import buy_hold, trend_200

AANDELEN = [
    "SPY", "QQQ", "DIA", "IWM", "XLK", "XLF", "XLE", "XLV", "XLY", "XLI", "XLU", "GLD",
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "AVGO", "NFLX",
    "COST", "JPM", "V", "MA", "UNH", "LLY", "XOM", "WMT", "HD", "KO", "PEP", "ORCL",
    "CRM", "ADBE", "INTC", "ASML", "CAT", "DIS",
]


def goed(bot, zelf):
    """De bot werkte goed als hij meer winst per 'risico' haalde dan zelf vasthouden."""
    return bot["per jaar"] / -bot["max daling"] > zelf["per jaar"] / -zelf["max daling"]


def main():
    rijen = []
    for sym in AANDELEN:
        try:
            df = get_daily_bars(sym, days=int(8 * 365.25))
        except Exception:
            continue
        helft = len(df) // 2
        delen = [df.iloc[:helft], df.iloc[helft:]]
        werkt = all(goed(run(d, trend_200), run(d, buy_hold)) for d in delen)
        bot, zelf = run(df, trend_200), run(df, buy_hold)
        rijen.append({
            "aandeel": sym,
            "bot per jaar": bot["per jaar"],
            "zelf per jaar": zelf["per jaar"],
            "ergste daling bot": bot["max daling"],
            "ergste daling zelf": zelf["max daling"],
            "werkt": werkt,
        })
        print(f"{sym} getest")

    t = pd.DataFrame(rijen)
    top = t[t.werkt].sort_values("bot per jaar", ascending=False)
    print(f"\nDe taktiek werkte in beide periodes bij {len(top)} van de {len(t)} aandelen.")
    print("Dit zijn ze, beste eerst:\n")
    top = top.drop(columns="werkt").set_index("aandeel")
    top.index.name = None
    for c in top.columns:
        top[c] = top[c].map(lambda v: f"{v:+.0%}")
    print(top.head(10).to_string())


if __name__ == "__main__":
    main()
