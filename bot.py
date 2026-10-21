"""Alpaca trading bot (paper trading).

Kies hieronder een strategie uit strategies.py. Test hem eerst met backtest.py.
De bot handelt één keer per dag, vlak voor de beurs sluit, net als in de backtest.
"""
import time
from datetime import datetime, timedelta

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from data import API_KEY, SECRET_KEY, get_daily_bars
from strategies import STRATEGIES

# --- Instellingen ---
SYMBOL = "NFLX"
STRATEGY = "trend_200"   # buy_hold, sma_cross, trend_200, rsi2, breakout
BUDGET = 10_000          # dollar per trade
TRADE_MINUTES_BEFORE_CLOSE = 10
CHECK_EVERY_SEC = 60
PAPER = True             # NIET aanpassen tot je weet wat je doet

trading = TradingClient(API_KEY, SECRET_KEY, paper=PAPER)
strategy = STRATEGIES[STRATEGY]


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
    df = get_daily_bars(SYMBOL, days=400)
    signal = int(strategy(df).iloc[-1])
    price = df.close.iloc[-1]
    held = current_qty(SYMBOL)
    print(f"{datetime.now():%Y-%m-%d %H:%M} {SYMBOL} prijs={price:.2f} "
          f"signaal={'HOUDEN' if signal else 'NIKS'} positie={held}")

    if signal == 1 and held == 0:
        qty = int(BUDGET // price)
        if qty > 0:
            order(OrderSide.BUY, qty)
    elif signal == 0 and held > 0:
        order(OrderSide.SELL, held)


def main():
    acct = trading.get_account()
    print(f"Account: {'PAPER' if PAPER else 'LIVE'} | cash=${float(acct.cash):,.2f} "
          f"| equity=${float(acct.equity):,.2f}")
    print(f"Strategie: {STRATEGY} op {SYMBOL}, handelt {TRADE_MINUTES_BEFORE_CLOSE} min voor slot")
    last_trade_day = None
    while True:
        try:
            clock = trading.get_clock()
            to_close = clock.next_close - clock.timestamp
            today = clock.timestamp.date()
            if not clock.is_open:
                print(f"{datetime.now():%H:%M} markt dicht, opent {clock.next_open:%a %H:%M} (NY-tijd)")
                time.sleep(60 * 30)
                continue
            if to_close <= timedelta(minutes=TRADE_MINUTES_BEFORE_CLOSE) and last_trade_day != today:
                step()
                last_trade_day = today
        except Exception as e:
            print("Fout:", e)
        time.sleep(CHECK_EVERY_SEC)


if __name__ == "__main__":
    main()
