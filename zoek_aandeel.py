"""Zoekt combinaties van aandeel + taktiek die goed werkten.

    python zoek_aandeel.py            -> S&P 500 + S&P 400 (ongeveer 900 aandelen), ~5-10 minuten
    python zoek_aandeel.py --snel     -> alleen de S&P 500

Test alle taktieken uit strategies.py over 8 jaar. Om geluk uit te sluiten splitsen we
die 8 jaar in twee stukken van 4 jaar: een combinatie telt alleen als hij in BEIDE stukken
beter was dan zelf vasthouden.
"""
import sys

import pandas as pd

from backtest import stats
from data import get_daily_bars_multi
from screener import cached, load_universe
from strategies import STRATEGIES

ETFS = ["SPY", "QQQ", "DIA", "IWM", "XLK", "XLF", "XLE", "XLV", "XLY", "XLI", "XLU", "XLP", "GLD", "TLT"]

UITLEG = {
    "trend_200": "in het aandeel zolang de koers boven het 200-dagen gemiddelde staat",
    "trend_50": "in het aandeel zolang de koers boven het 50-dagen gemiddelde staat",
    "sma_cross": "kopen als het 10-dagen gemiddelde boven het 30-dagen gemiddelde komt",
    "golden_cross": "kopen als het 50-dagen gemiddelde boven het 200-dagen gemiddelde komt",
    "ema_cross": "kopen als het 20-dagen gemiddelde boven het 50-dagen gemiddelde komt",
    "macd": "kopen als de MACD (een snelheidsmeter van de koers) omhoog draait",
    "momentum_12m": "in het aandeel als het het afgelopen jaar gestegen is",
    "rsi2": "dipjes kopen in een stijgend aandeel, na een paar dagen weer verkopen",
    "bollinger": "kopen na een flinke dip in een stijgend aandeel, verkopen als hij hersteld is",
    "trend_rsi": "na een dip instappen in een stijgend aandeel, vasthouden tot de trend breekt",
    "breakout": "kopen bij een nieuw 55-dagen record, verkopen bij een 20-dagen dieptepunt",
    "breakout_20": "kopen bij een nieuw 20-dagen record, verkopen bij een 10-dagen dieptepunt",
}


def goed(bot, zelf):
    """Goed = meer winst per 'risico' (winst per jaar gedeeld door ergste daling) dan zelf vasthouden."""
    return bot["per jaar"] / -bot["max daling"] > zelf["per jaar"] / -zelf["max daling"]


def main():
    universes = ["sp500"] if "--snel" in sys.argv else ["sp500", "sp400"]
    symbols = ETFS + sorted({s for u in universes for s in load_universe(u).symbol} - set(ETFS))
    print(f"Koersen ophalen voor {len(symbols)} aandelen (8 jaar)...")
    bars = cached("daily8y_" + "_".join(universes), lambda: get_daily_bars_multi(symbols, int(8 * 365.25)))

    rijen = []
    for n, (sym, df) in enumerate(bars.items(), 1):
        if len(df) < 1900:  # minder dan ~7,5 jaar geschiedenis: overslaan
            continue
        helft = len(df) // 2
        delen = [slice(0, helft), slice(helft, len(df))]
        hold = pd.Series(1, index=df.index)
        zelf = stats(df, hold)
        zelf_delen = [stats(df.iloc[d], hold.iloc[d]) for d in delen]
        for naam, taktiek in STRATEGIES.items():
            if naam == "buy_hold":
                continue
            pos = taktiek(df)
            bot = stats(df, pos)
            werkt = all(goed(stats(df.iloc[d], pos.iloc[d]), z) for d, z in zip(delen, zelf_delen))
            rijen.append({"aandeel": sym, "taktiek": naam, "bot per jaar": bot["per jaar"],
                          "zelf per jaar": zelf["per jaar"], "ergste daling bot": bot["max daling"],
                          "ergste daling zelf": zelf["max daling"], "werkt": werkt})
        if n % 100 == 0:
            print(f"  {n}/{len(bars)} getest")

    t = pd.DataFrame(rijen)
    pct = lambda v: f"{v:+.0%}"

    print(f"\n===== 1. WELKE TAKTIEK WERKT HET VAAKST?  ({t.aandeel.nunique()} aandelen getest)")
    per = t.groupby("taktiek").agg(
        werkt_bij=("werkt", "mean"),
        bot_per_jaar=("bot per jaar", "median"),
        zelf_per_jaar=("zelf per jaar", "median"),
        daling_bot=("ergste daling bot", "median"),
        daling_zelf=("ergste daling zelf", "median"),
    ).sort_values("werkt_bij", ascending=False)
    per.index.name = None
    per.columns = ["werkt bij", "bot per jaar", "zelf per jaar", "ergste daling bot", "ergste daling zelf"]
    per["werkt bij"] = per["werkt bij"].map(lambda v: f"{v:.0%} van de aandelen")
    for c in per.columns[1:]:
        per[c] = per[c].map(pct)
    print("(per jaar en daling = wat een gemiddeld aandeel deed)")
    print("Let op: met puur willekeurige koersen 'werkt' een taktiek ook bij ongeveer 10-15% van de aandelen.")
    print("Pas als een taktiek daar duidelijk boven zit, is er echt iets aan de hand.")
    print(per.to_string())

    top = t[t.werkt].sort_values("bot per jaar", ascending=False).head(20)
    print(f"\n===== 2. DE 20 BESTE COMBINATIES  ({t.werkt.sum()} van de {len(t)} werkten in beide periodes)")
    top = top.drop(columns="werkt").set_index("aandeel")
    top.index.name = None
    for c in top.columns[1:]:
        top[c] = top[c].map(pct)
    print(top.to_string())

    print("\nWat de taktieken doen:")
    for naam in per.index:
        print(f"  {naam}: {UITLEG[naam]}")


if __name__ == "__main__":
    main()
