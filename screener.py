"""Aandelen-screener. Elke run wordt opgeslagen in screens.json (datum, filters, aantallen per stap, picks).

    python screener.py momentum             -> mid-cap groeiaandelen met sterk momentum
    python screener.py quality              -> insider-aankopen, vrije kasstroom, earnings surprises,
                                               analisten steeds positiever; gerangschikt op totaalscore
    python screener.py momentum --top 20 --universe sp600
    python screener.py history              -> eerdere runs bekijken

Koersen komen van Alpaca, bedrijfscijfers van Yahoo Finance (yfinance).
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

from data import get_daily_bars_multi

STATE = Path(__file__).with_name("screens.json")
CACHE = Path(__file__).with_name("cache")
UNIVERSES = {
    "sp400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",   # mid-caps
    "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",   # large-caps
    "sp600": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",   # small-caps
}


# ---------- data ----------

def cached(name, fn):
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"{name}_{datetime.now():%Y%m%d}.pkl"
    if f.exists():
        return pd.read_pickle(f)
    value = fn()
    pd.to_pickle(value, f)
    return value


def load_universe(name):
    def fetch():
        html = requests.get(UNIVERSES[name], headers={"User-Agent": "Mozilla/5.0 trade-bot"}, timeout=30).text
        table = next(t for t in pd.read_html(StringIO(html)) if "Symbol" in t.columns)
        return pd.DataFrame({
            "symbol": table["Symbol"].astype(str).str.replace("-", ".", regex=False),
            "naam": table["Security"],
            "sector": table.get("GICS Sector", ""),
        })
    return cached(f"universe_{name}", fetch)


def yahoo(sym):
    return yf.Ticker(sym.replace(".", "-"))


def parallel(fn, items, workers=6):
    def safe(x):
        try:
            return fn(x)
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(items, pool.map(safe, items)))


def pct_rank(s):
    return s.rank(pct=True)


# ---------- screen 1: mid-cap groei + momentum ----------

def screen_momentum(args):
    filters = {
        "universe": args.universe,
        "min_market_cap": args.min_cap,
        "max_market_cap": args.max_cap,
        "min_revenue_growth": args.min_growth,
        "min_avg_dollar_volume": 20_000_000,
        "trend": "koers boven 200-daags gemiddelde",
        "momentum": "12-1 maanden rendement (laatste maand niet meegeteld) + 6 maanden rendement",
        "top": args.top,
    }
    uni = load_universe(args.universe)
    counts = {"universe": len(uni)}

    print(f"Koersen ophalen voor {len(uni)} aandelen...")
    bars = cached(f"daily_{args.universe}", lambda: get_daily_bars_multi(list(uni.symbol), 420))
    rows = []
    for sym, df in bars.items():
        c, v = df.close, df.volume
        if len(c) < 253:
            continue
        rows.append({
            "symbol": sym,
            "prijs": c.iloc[-1],
            "mom_12_1": c.iloc[-22] / c.iloc[-253] - 1,
            "rend_6m": c.iloc[-1] / c.iloc[-127] - 1,
            "boven_sma200": c.iloc[-1] > c.iloc[-200:].mean(),
            "dollar_volume": (c.iloc[-20:] * v.iloc[-20:]).mean(),
        })
    df = pd.DataFrame(rows)
    counts["met_koersen"] = len(df)
    df = df[df.boven_sma200 & (df.dollar_volume >= filters["min_avg_dollar_volume"])]
    counts["trend_en_liquiditeit"] = len(df)
    df["momentum_score"] = (pct_rank(df.mom_12_1) + pct_rank(df.rend_6m)) / 2
    # Alleen de sterkste 100 bij Yahoo checken, scheelt veel tijd.
    df = df.sort_values("momentum_score", ascending=False).head(100)

    print(f"Bedrijfscijfers ophalen voor {len(df)} kandidaten...")
    info = parallel(lambda s: yahoo(s).info, list(df.symbol))
    df["market_cap"] = df.symbol.map(lambda s: (info.get(s) or {}).get("marketCap"))
    df["omzetgroei"] = df.symbol.map(lambda s: (info.get(s) or {}).get("revenueGrowth"))
    df = df.dropna(subset=["market_cap", "omzetgroei"])
    df = df[(df.market_cap >= args.min_cap) & (df.market_cap <= args.max_cap)]
    counts["mid_cap"] = len(df)
    df = df[df.omzetgroei >= args.min_growth]
    counts["groei"] = len(df)

    picks = df.sort_values("momentum_score", ascending=False).head(args.top).merge(uni, on="symbol", how="left")
    cols = ["symbol", "naam", "sector", "prijs", "market_cap", "omzetgroei", "mom_12_1", "rend_6m", "momentum_score"]
    return filters, counts, picks[cols]


# ---------- screen 2: insiders, kasstroom, surprises, analisten ----------

def quality_data(sym):
    """Haalt per aandeel de 4 factoren op. Stopt zodra een harde eis niet gehaald wordt."""
    t = yahoo(sym)
    info = t.info
    fcf, cap = info.get("freeCashflow"), info.get("marketCap")
    if not fcf or not cap or fcf <= 0:
        return {"stop": "fcf"}
    eh = t.earnings_history
    if eh is None or eh.empty or "surprisePercent" not in eh:
        return {"stop": "surprise"}
    surprises = eh["surprisePercent"].dropna().tail(4)
    if surprises.empty or surprises.iloc[-1] <= 0:
        return {"stop": "surprise"}
    ip = t.insider_purchases
    if ip is None or ip.empty:
        return {"stop": "insiders"}
    ip = ip.set_index(ip.columns[0])
    buys = ip.loc["Purchases", "Trans"]
    net_pct = ip.loc["% Net Shares Purchased (Sold)", "Shares"]
    if pd.isna(buys) or buys < 1 or pd.isna(net_pct) or net_pct <= 0:
        return {"stop": "insiders"}
    rec = t.recommendations
    if rec is None or rec.empty:
        return {"stop": "analisten"}
    rec = rec.set_index("period")

    def sentiment(p):
        r = rec.loc[p]
        n = r[["strongBuy", "buy", "hold", "sell", "strongSell"]].sum()
        return (2 * r.strongBuy + r.buy - r.sell - 2 * r.strongSell) / n if n else 0

    oldest = "-3m" if "-3m" in rec.index else rec.index[-1]
    change = sentiment("0m") - sentiment(oldest)
    if change < 0:
        return {"stop": "analisten"}
    return {
        "market_cap": cap, "fcf_yield": fcf / cap,
        "insider_kopen": int(buys), "insider_netto_%": float(net_pct),
        "laatste_surprise": float(surprises.iloc[-1]), "gem_surprise_4k": float(surprises.mean()),
        "analisten_nu": sentiment("0m"), "analisten_verandering": change,
    }


def screen_quality(args):
    filters = {
        "universe": args.universe,
        "insiders": "minstens 1 insider-aankoop en netto meer gekocht dan verkocht (laatste 6 maanden)",
        "vrije_kasstroom": "positief; score = free cash flow / market cap",
        "earnings_surprise": "laatste kwartaal boven verwachting; score = gemiddelde surprise 4 kwartalen",
        "analisten": "sentiment nu >= 3 maanden geleden; score = verbetering",
        "ranking": "gemiddelde percentielrang van de 4 scores",
        "top": args.top,
    }
    uni = load_universe(args.universe)
    print(f"Bedrijfscijfers ophalen voor {len(uni)} aandelen (duurt een paar minuten)...")
    data = cached(f"quality_{args.universe}", lambda: parallel(quality_data, list(uni.symbol)))

    stops = pd.Series([d.get("stop") if d else "geen data" for d in data.values()]).value_counts()
    counts = {"universe": len(uni)}
    left = len(uni) - stops.get("geen data", 0)
    counts["met_data"] = left
    for stage in ["fcf", "surprise", "insiders", "analisten"]:
        left -= stops.get(stage, 0)
        counts[f"na_{stage}"] = int(left)

    df = pd.DataFrame([{"symbol": s, **d} for s, d in data.items() if d and "stop" not in d])
    if df.empty:
        return filters, counts, df
    df["score"] = (pct_rank(df.fcf_yield) + pct_rank(df["insider_netto_%"]) +
                   pct_rank(df.gem_surprise_4k) + pct_rank(df.analisten_verandering)) / 4
    picks = df.sort_values("score", ascending=False).head(args.top).merge(uni, on="symbol", how="left")
    cols = ["symbol", "naam", "sector", "score", "fcf_yield", "insider_kopen", "insider_netto_%",
            "gem_surprise_4k", "analisten_verandering", "market_cap"]
    return filters, counts, picks[cols]


# ---------- state ----------

def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {"runs": []}


def save_run(screen, filters, counts, picks):
    state = load_state()
    previous = next((r for r in reversed(state["runs"]) if r["screen"] == screen), None)
    symbols = list(picks.symbol) if not picks.empty else []
    run = {
        "id": len(state["runs"]) + 1,
        "screen": screen,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filters": filters,
        "counts": counts,
        "picks": json.loads(picks.to_json(orient="records")) if symbols else [],
        "nieuw_sinds_vorige": [s for s in symbols if previous and s not in previous["symbols"]],
        "weg_sinds_vorige": [s for s in previous["symbols"] if s not in symbols] if previous else [],
        "symbols": symbols,
    }
    state["runs"].append(run)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    return run, previous


def show_history():
    runs = load_state()["runs"]
    if not runs:
        print("Nog geen runs opgeslagen.")
    for r in runs:
        print(f"#{r['id']:<3} {r['run_at'][:16].replace('T', ' ')}  {r['screen']:<9} "
              f"{len(r['symbols'])} picks: {', '.join(r['symbols'])}")


# ---------- main ----------

def fmt(picks):
    t = picks.copy()
    for c in ["omzetgroei", "mom_12_1", "rend_6m", "fcf_yield", "gem_surprise_4k", "insider_netto_%"]:
        if c in t:
            t[c] = t[c].map(lambda v: f"{v:+.1%}")
    for c in ["momentum_score", "score", "analisten_verandering"]:
        if c in t:
            t[c] = t[c].map(lambda v: f"{v:.2f}")
    if "market_cap" in t:
        t["market_cap"] = t["market_cap"].map(lambda v: f"${v / 1e9:.1f}B")
    if "prijs" in t:
        t["prijs"] = t["prijs"].map(lambda v: f"${v:.2f}")
    t["naam"] = t["naam"].astype(str).str.slice(0, 24)
    t.index = range(1, len(t) + 1)
    return t.to_string()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("screen", choices=["momentum", "quality", "history"])
    p.add_argument("--universe", choices=list(UNIVERSES), default="sp400")
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--min-cap", type=float, default=2e9)
    p.add_argument("--max-cap", type=float, default=15e9)
    p.add_argument("--min-growth", type=float, default=0.15)
    args = p.parse_args()

    if args.screen == "history":
        return show_history()
    fn = screen_momentum if args.screen == "momentum" else screen_quality
    filters, counts, picks = fn(args)
    run, previous = save_run(args.screen, filters, counts, picks)

    print(f"\n=== {args.screen.upper()} screen #{run['id']}  ({run['run_at'][:16].replace('T', ' ')} UTC)")
    print("Aantal over per stap: " + " -> ".join(f"{k} {v}" for k, v in counts.items()))
    print(fmt(picks) if not picks.empty else "Geen aandelen voldoen aan alle eisen.")
    if previous:
        print(f"\nT.o.v. vorige run (#{previous['id']}): nieuw {run['nieuw_sinds_vorige'] or '-'}, "
              f"weg {run['weg_sinds_vorige'] or '-'}")
    print(f"Opgeslagen in {STATE.name}")


if __name__ == "__main__":
    main()
