"""Actieve nieuwsbot (paper trading).

Leest elke minuut het nieuws over het aandeel en handelt op sterk nieuws:
- Sterk positief nieuws + aandeel in een stijgende trend -> kopen,
  met automatische winstneming (TAKE_PROFIT) en stop-loss (STOP_LOSS).
- Sterk negatief nieuws terwijl we het aandeel hebben -> direct verkopen.
Alle beoordeelde artikelen komen in news_log.csv, zodat je later kunt zien hoe goed het werkt.
"""
import csv
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (
    GetOrdersRequest, MarketOrderRequest, StopLossRequest, TakeProfitRequest,
)

import news
from data import API_KEY, SECRET_KEY, get_daily_bars, get_price
from strategies import trend_200

# --- Instellingen ---
SYMBOL = "NVDA"
BUDGET = 10_000           # dollar per trade
BUY_SCORE = 0.6           # minimale nieuwsscore om te kopen (0 tot 1)
SELL_SCORE = -0.6         # nieuwsscore waarbij we verkopen
TAKE_PROFIT = 0.04        # verkoop automatisch bij +4%
STOP_LOSS = 0.02          # verkoop automatisch bij -2%
MAX_NEWS_AGE_MIN = 30     # ouder nieuws negeren (de markt heeft het dan al verwerkt)
COOLDOWN_MIN = 30         # na een trade even niks doen
CHECK_EVERY_SEC = 60
PAPER = True              # NIET aanpassen tot je weet wat je doet

LOG_FILE = Path(__file__).with_name("news_log.csv")
trading = TradingClient(API_KEY, SECRET_KEY, paper=PAPER)


def current_qty() -> float:
    try:
        return float(trading.get_open_position(SYMBOL).qty)
    except APIError:
        return 0.0


def in_uptrend() -> bool:
    return bool(trend_200(get_daily_bars(SYMBOL, days=400)).iloc[-1])


def buy(price: float):
    qty = int(BUDGET // price)
    if qty == 0:
        return
    o = trading.submit_order(MarketOrderRequest(
        symbol=SYMBOL, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=round(price * (1 + TAKE_PROFIT), 2)),
        stop_loss=StopLossRequest(stop_price=round(price * (1 - STOP_LOSS), 2)),
    ))
    print(f"  -> KOOP {qty} {SYMBOL} rond ${price:.2f} "
          f"(winst bij ${price * (1 + TAKE_PROFIT):.2f}, stop bij ${price * (1 - STOP_LOSS):.2f}) order {o.id}")


def sell_all():
    # Eerst de open winst/stop-orders annuleren, anders zijn de aandelen 'bezet'.
    for o in trading.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[SYMBOL])):
        trading.cancel_order_by_id(o.id)
    time.sleep(2)
    trading.close_position(SYMBOL)
    print(f"  -> VERKOOP alles van {SYMBOL}")


def log(article, s, reason, action):
    new = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["tijd", "nieuws_tijd", "score", "actie", "kop", "uitleg", "url"])
        w.writerow([f"{datetime.now():%Y-%m-%d %H:%M}", f"{article.created_at:%Y-%m-%d %H:%M}",
                    f"{s:+.2f}", action, article.headline, reason, article.url])


def main():
    acct = trading.get_account()
    print(f"Account: {'PAPER' if PAPER else 'LIVE'} | cash=${float(acct.cash):,.2f} "
          f"| equity=${float(acct.equity):,.2f}")
    print(f"Nieuwsbot op {SYMBOL}, nieuws beoordeeld door: {news.USING}")
    since = datetime.now(timezone.utc) - timedelta(minutes=MAX_NEWS_AGE_MIN)
    last_trade = datetime.min.replace(tzinfo=timezone.utc)

    while True:
        try:
            clock = trading.get_clock()
            if not clock.is_open:
                print(f"{datetime.now():%H:%M} markt dicht, opent {clock.next_open:%a %H:%M} (NY-tijd)")
                time.sleep(60 * 15)
                since = datetime.now(timezone.utc) - timedelta(minutes=MAX_NEWS_AGE_MIN)
                continue

            now = datetime.now(timezone.utc)
            articles = news.fetch_news(SYMBOL, since)
            if articles:
                since = max(a.created_at for a in articles)
            for a in articles:
                if now - a.created_at > timedelta(minutes=MAX_NEWS_AGE_MIN):
                    continue
                s, reason = news.score(SYMBOL, a)
                print(f"{datetime.now():%H:%M} [{s:+.2f}] {a.headline}\n         {reason}")

                action = "-"
                held = current_qty()
                cooling = now - last_trade < timedelta(minutes=COOLDOWN_MIN)
                if s >= BUY_SCORE and held == 0 and not cooling:
                    if in_uptrend():
                        buy(get_price(SYMBOL))
                        action, last_trade = "koop", now
                    else:
                        action = "geen koop (geen stijgende trend)"
                        print(f"  {action}")
                elif s <= SELL_SCORE and held > 0:
                    sell_all()
                    action, last_trade = "verkoop", now
                log(a, s, reason, action)
        except Exception as e:
            print("Fout:", e)
        time.sleep(CHECK_EVERY_SEC)


if __name__ == "__main__":
    main()
