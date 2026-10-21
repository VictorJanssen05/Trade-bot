"""Daytrade-bot (paper trading): krijgt elke minuut live de koers binnen en handelt
met een strategie uit intraday.py. Verkoopt alles om 15:55 (New York), dus nooit 's nachts in een aandeel.

Test eerst met intraday_backtest.py welke strategie werkt en zet die hieronder bij STRATEGY.
Draai niet tegelijk met news_bot.py op dezelfde aandelen.
"""
import asyncio
import time
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from alpaca.data.live import StockDataStream
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from data import API_KEY, SECRET_KEY, get_today_bars
from intraday import STRATEGIES, Runner, minutes

# --- Instellingen ---
SYMBOLS = ["NVDA", "AAPL", "AMD", "MSFT", "META"]
STRATEGY = "ma_10_50"        # ma_5_20, ma_10_50, ma_20_100, ma_50_200, opening_range, vwap_dip, momentum
BUDGET = 10_000              # dollar per aandeel per trade
PAPER = True                 # NIET aanpassen tot je weet wat je doet

NY = ZoneInfo("America/New_York")
trading = TradingClient(API_KEY, SECRET_KEY, paper=PAPER)
runners = {s: Runner(STRATEGIES[STRATEGY]()) for s in SYMBOLS}


def to_bar(t, o, h, l, c, v):
    return SimpleNamespace(t=t, open=o, high=h, low=l, close=c, volume=v)


def warm_up():
    """Bij (her)starten midden op de dag: de minuten van vandaag naspelen zonder te handelen,
    en kijken welke aandelen we al hebben."""
    held = {p.symbol: float(p.avg_entry_price) for p in trading.get_all_positions()}
    for sym, r in runners.items():
        bars = get_today_bars(sym)
        for t, row in bars.iterrows():
            if 9 * 60 + 30 <= minutes(t) < 16 * 60:
                r.on_bar(to_bar(t, row.open, row.high, row.low, row.close, row.volume))
        if sym in held:
            r.in_pos = True
            r.s.on_fill(held[sym])
        print(f"{sym}: {len(bars)} minuten van vandaag ingeladen"
              f"{', heeft al een positie' if sym in held else ''}")


def buy(sym, price):
    qty = int(BUDGET // price)
    if qty:
        trading.submit_order(MarketOrderRequest(symbol=sym, qty=qty, side=OrderSide.BUY,
                                                time_in_force=TimeInForce.DAY))
        print(f"  -> KOOP {qty} {sym} rond ${price:.2f}")
    return qty > 0


def sell(sym, price):
    trading.close_position(sym)
    print(f"  -> VERKOOP {sym} rond ${price:.2f}")


async def on_bar(bar):
    t = bar.timestamp.astimezone(NY)
    if not 9 * 60 + 30 <= minutes(t) < 16 * 60:
        return
    r = runners[bar.symbol]
    action = r.on_bar(to_bar(t, bar.open, bar.high, bar.low, bar.close, bar.volume))
    if action is None:
        return
    print(f"{datetime.now():%H:%M:%S} {bar.symbol} ${bar.close:.2f} -> {action}")
    try:
        if action == "buy" and await asyncio.to_thread(buy, bar.symbol, bar.close):
            r.in_pos = True
            r.s.on_fill(bar.close)
        elif action == "sell":
            await asyncio.to_thread(sell, bar.symbol, bar.close)
            r.in_pos = False
    except Exception as e:
        print(f"  Order fout bij {bar.symbol}: {e}")


def main():
    acct = trading.get_account()
    print(f"Account: {'PAPER' if PAPER else 'LIVE'} | cash=${float(acct.cash):,.2f} "
          f"| equity=${float(acct.equity):,.2f}")
    print(f"Daytrade-bot: {STRATEGY} op {', '.join(SYMBOLS)}")
    warm_up()
    while True:
        stream = StockDataStream(API_KEY, SECRET_KEY)
        stream.subscribe_bars(on_bar, *SYMBOLS)
        print("Live koersen aan het volgen... (elke minuut een update per aandeel)")
        try:
            stream.run()
        except Exception as e:
            print("Verbinding weg:", e)
        time.sleep(10)


if __name__ == "__main__":
    main()
