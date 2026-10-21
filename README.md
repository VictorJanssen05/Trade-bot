# Trade-bot

Alpaca trading bot (paper trading / nepgeld) met meerdere strategieën en een backtest.

## Starten

1. Maak paper API keys aan op https://app.alpaca.markets (Paper Trading -> API Keys).
2. Kopieer `.env.example` naar `.env` en vul je keys in.
3. Installeer en draai:

```bash
python -m venv .venv
.venv\Scripts\activate        # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

## Strategie kiezen

1. Test eerst welke strategie het best werkt: `python backtest.py` (Nvidia) of `python backtest.py AAPL TSLA`.
2. Zet de beste bovenaan `bot.py` bij `STRATEGY`.

Strategieën staan in `strategies.py`: `buy_hold`, `sma_cross`, `trend_200`, `rsi2`, `breakout`.

## Nieuwsbot (actief)

`python news_bot.py` leest elke minuut het nieuws over NVDA (via Alpaca) en handelt op sterk nieuws:
koopt bij sterk positief nieuws als het aandeel in een stijgende trend zit (met automatische
winstneming en stop-loss), en verkoopt bij sterk negatief nieuws. Elk artikel en elke beslissing
komt in `news_log.csv`.

Zet optioneel `ANTHROPIC_API_KEY` in `.env` zodat Claude het nieuws beoordeelt in plaats van
een simpele woordenlijst.

## Op een Raspberry Pi draaien (24/7)

```bash
sudo apt update && sudo apt install -y git python3-venv
git clone https://github.com/VictorJanssen05/Trade-bot.git ~/Trade-bot
cd ~/Trade-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env      # keys invullen, opslaan met Ctrl+O, Enter, Ctrl+X
```

Automatisch starten bij opstarten en herstarten als hij crasht:

```bash
sudo tee /etc/systemd/system/trade-bot.service > /dev/null <<EOT
[Unit]
Description=Alpaca news trade bot
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$HOME/Trade-bot
ExecStart=$HOME/Trade-bot/.venv/bin/python -u news_bot.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOT
sudo systemctl daemon-reload
sudo systemctl enable --now trade-bot
```

- Meekijken: `journalctl -u trade-bot -f` (stoppen met Ctrl+C, de bot draait door)
- Stoppen / starten: `sudo systemctl stop trade-bot` / `sudo systemctl start trade-bot`
- Updaten: `cd ~/Trade-bot && git pull && sudo systemctl restart trade-bot`
