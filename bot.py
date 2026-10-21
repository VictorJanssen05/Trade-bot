"""Simpele Alpaca trading bot (paper trading).

Strategie: SMA crossover.
- Korte gemiddelde (SMA_FAST) boven lange (SMA_SLOW) -> kopen als we nog niks hebben.
- Korte onder lange -> alles verkopen.
"""
import os
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from alpaca.common.exceptions import APIError
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

# --- Instellingen ---
SYMBOL = "AAPL"
QTY = 1                 # aantal aandelen per trade
SMA_FAST = 10           # dagen
SMA_SLOW = 30           # dagen
CHECK_EVERY_SEC = 60 * 15
PAPER = True            # NIET aanpassen tot je weet wat je doet

load_dotenv()
API_KEY = os.environ["ALPACA_API_KEY"]
SECRET_KEY = os.environ["ALPACA_SECRET_KEY"]

trading = TradingClient(API_KEY, SECRET_KEY, paper=PAPER)
data = StockHistoricalDataClient(API_KEY, SECRET_KEY)


def get_closes(symbol: str):
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=datetime.now(timezone.utc) - timedelta(days=SMA_SLOW * 3),
        feed="iex",  # gratis datafeed
    )
    return data.get_stock_bars(req).df.loc[symbol]["close"]


def current_qty(symbol: str) -> float:
    try:
        return float(trading.get_open_position(symbol).qty)
    except APIError:
        return 0.0


def order(side: OrderSide, qty: float):
    o = trading.submit_order(MarketOrderRequest(
        symbol=SYMBOL, qty=qty, side=side, time_in_force=TimeInForce.DAY,
    ))
    print(f"  -> {side.value} {qty} {SYMBOL} (order {o.id})")


def step():
    closes = get_closes(SYMBOL)
    fast = closes.rolling(SMA_FAST).mean().iloc[-1]
    slow = closes.rolling(SMA_SLOW).mean().iloc[-1]
    held = current_qty(SYMBOL)
    print(f"{datetime.now():%H:%M:%S} {SYMBOL} prijs={closes.iloc[-1]:.2f} "
          f"fast={fast:.2f} slow={slow:.2f} positie={held}")

    if fast > slow and held == 0:
        order(OrderSide.BUY, QTY)
    elif fast < slow and held > 0:
        order(OrderSide.SELL, held)


def main():
    acct = trading.get_account()
    print(f"Account: {'PAPER' if PAPER else 'LIVE'} | cash=${float(acct.cash):,.2f} "
          f"| equity=${float(acct.equity):,.2f}")
    while True:
        try:
            if trading.get_clock().is_open:
                step()
            else:
                print(f"{datetime.now():%H:%M:%S} markt dicht, wachten...")
        except Exception as e:
            print("Fout:", e)
        time.sleep(CHECK_EVERY_SEC)


if __name__ == "__main__":
    main()
