"""Zoekt combinaties van aandeel + taktiek die goed werkten.

    python zoek_aandeel.py

Test alle taktieken uit strategies.py op ongeveer 60 aandelen.

Om geluk uit te sluiten testen we de afgelopen 8 jaar in twee stukken van 4 jaar.
Alleen als de taktiek in BEIDE stukken goed werkte, telt het.
"""
import pandas as pd

from backtest import run
from data import get_daily_bars
from strategies import STRATEGIES, buy_hold

AANDELEN = [
    "SPY", "QQQ", "DIA", "IWM", "XLK", "XLF", "XLE", "XLV", "XLY", "XLI", "XLU", "GLD",
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "AVGO", "NFLX",
    "COST", "JPM", "V", "MA", "UNH", "LLY", "XOM", "WMT", "HD", "KO", "PEP", "ORCL",
    "CRM", "ADBE", "INTC", "ASML", "CAT", "DIS",
    "NOW", "INTU", "ISRG", "ANET", "LRCX", "KLAC", "AMAT", "MU", "TSM", "SHOP",
    "MELI", "CMG", "DECK", "AXON", "TTD", "FICO", "CDNS", "SNPS", "MPWR", "ENPH",
]

UITLEG = {
    "trend_200": "in het aandeel zolang de koers boven het 200-dagen gemiddelde staat",
    "sma_cross": "kopen als het 10-dagen gemiddelde boven het 30-dagen gemiddelde komt",
    "rsi2": "dipjes kopen in een stijgend aandeel, na een paar dagen weer verkopen",
    "breakout": "kopen bij een nieuw 55-dagen record, verkopen bij een 20-dagen dieptepunt",
}


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
        zelf = run(df, buy_hold)
        for naam, taktiek in STRATEGIES.items():
            if naam == "buy_hold":
                continue
            werkt = all(goed(run(d, taktiek), run(d, buy_hold)) for d in delen)
            bot = run(df, taktiek)
            rijen.append({
                "aandeel": sym,
                "taktiek": naam,
                "bot per jaar": bot["per jaar"],
                "zelf per jaar": zelf["per jaar"],
                "ergste daling bot": bot["max daling"],
                "ergste daling zelf": zelf["max daling"],
                "werkt": werkt,
            })
        print(f"{sym} getest")

    t = pd.DataFrame(rijen)
    top = t[t.werkt].sort_values("bot per jaar", ascending=False)
    print(f"\n{len(top)} van de {len(t)} combinaties werkten in beide periodes. De beste 10:\n")
    top = top.drop(columns="werkt").set_index("aandeel")
    top.index.name = None
    for c in top.columns[1:]:
        top[c] = top[c].map(lambda v: f"{v:+.0%}")
    print(top.head(10).to_string())
    print("\nWat de taktieken doen:")
    for naam in top.head(10).taktiek.unique():
        print(f"  {naam}: {UITLEG[naam]}")


if __name__ == "__main__":
    main()
