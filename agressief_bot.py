"""Agressieve Nvidia-bot (paper trading).

Taktiek: trend_200 (in Nvidia zolang de koers boven het 200-dagen gemiddelde staat),
maar met AL je geld en een hefboom: bij HEFBOOM = 2 leent hij bij Alpaca bij, zodat
je voor 2x je geld in Nvidia zit. Winst gaat 2x zo hard, verlies ook.

    python agressief_bot.py --test   -> eerst kijken wat dit de afgelopen 8 jaar had gedaan
    python agressief_bot.py          -> bot starten

Draai deze bot alleen, niet naast de andere bots: hij gebruikt al het geld op je account.
"""
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from data import API_KEY, SECRET_KEY, get_daily_bars
from strategies import trend_200

# --- Instellingen ---
SYMBOL = "NVDA"
HEFBOOM = 2.0            # 1 = alleen eigen geld, 2 = 2x zoveel (max bij Alpaca voor 's nachts)
RENTE = 0.07             # rente per jaar op geleend geld (bij echt geld; paper rekent niks)
TRADE_MINUTES_BEFORE_CLOSE = 10
PAPER = True             # NIET aanpassen tot je weet wat je doet


def test():
    df = get_daily_bars(SYMBOL, days=int(8 * 365.25))
    ret = df.close.pct_change().fillna(0)
    pos = trend_200(df).shift(1).fillna(0)
    years = len(df) / 252
    rows = {}
    for naam, p, lev in [("zelf vasthouden", 1, 1), ("bot zonder hefboom", pos, 1), (f"bot met {HEFBOOM:g}x hefboom", pos, HEFBOOM)]:
        p = pd.Series(p, index=df.index) if not isinstance(p, pd.Series) else p
        trades = p.diff().abs().fillna(p.iloc[0])
        daily = p * (ret * lev - (lev - 1) * RENTE / 252) - trades * 0.0005
        eq = (1 + daily).cumprod()
        rows[naam] = {
            "per jaar": f"{eq.iloc[-1] ** (1 / years) - 1:+.0%}",
            "$10.000 werd": f"${10_000 * eq.iloc[-1]:,.0f}",
            "ergste daling": f"{(eq / eq.cummax() - 1).min():+.0%}",
        }
    print(f"{SYMBOL}, {df.index[0]:%Y} t/m {df.index[-1]:%Y}:\n")
    print(pd.DataFrame(rows).T.to_string())


def run_bot():
    trading = TradingClient(API_KEY, SECRET_KEY, paper=PAPER)
    acct = trading.get_account()
    print(f"Account: {'PAPER' if PAPER else 'LIVE'} | equity=${float(acct.equity):,.2f}")
    print(f"Agressieve bot: {SYMBOL}, trend_200, hefboom {HEFBOOM:g}x")
    last_day = None
    while True:
        try:
            clock = trading.get_clock()
            if not clock.is_open:
                time.sleep(60 * 15)
                continue
            if clock.next_close - clock.timestamp > timedelta(minutes=TRADE_MINUTES_BEFORE_CLOSE) \
                    or last_day == clock.timestamp.date():
                time.sleep(60)
                continue
            last_day = clock.timestamp.date()

            df = get_daily_bars(SYMBOL, days=400)
            signal, price = int(trend_200(df).iloc[-1]), df.close.iloc[-1]
            try:
                held = float(trading.get_open_position(SYMBOL).qty)
            except APIError:
                held = 0.0
            print(f"{datetime.now():%Y-%m-%d %H:%M} {SYMBOL} ${price:.2f} "
                  f"signaal={'IN' if signal else 'UIT'} positie={held:g}")
            if signal and held == 0:
                equity = float(trading.get_account().equity)
                qty = int(equity * HEFBOOM * 0.98 // price)  # 2% marge voor prijsverschil
                trading.submit_order(MarketOrderRequest(symbol=SYMBOL, qty=qty, side=OrderSide.BUY,
                                                        time_in_force=TimeInForce.DAY))
                print(f"  -> KOOP {qty} {SYMBOL} (~${qty * price:,.0f})")
            elif not signal and held > 0:
                trading.close_position(SYMBOL)
                print(f"  -> VERKOOP alles")
        except Exception as e:
            print("Fout:", e)
        time.sleep(60)


if __name__ == "__main__":
    test() if "--test" in sys.argv else run_bot()
