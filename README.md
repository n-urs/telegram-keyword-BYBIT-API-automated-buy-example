# Telegram Bybit Auto-Trader Bot

A Python-based Telegram bot that listens for token launch/list announcements, executes market buys on Bybit, and places dynamic take-profit or market-sell orders based on configurable market-cap thresholds.

---

## 🚀 Features

* **Telegram Monitoring**: Listens in specified Telegram channels for keywords:

  * `futures will launch`
  * `will list`
* **Automated Buys**: Splits a fixed USDT amount across detected tokens and places market-buy orders.
* **Dynamic Take-Profit**: Calculates take-profit levels using live k-line data and adjusts multipliers based on real-time market capitalization.
* **Cooldown Mechanism**: Prevents repeated buys of the same token within a configurable interval.
* **Dual Market-Cap Sources**: Queries CoinMarketCap first, falls back to CoinGecko if needed.
* **Robust Logging & Error Handling**

---

## 📦 Prerequisites

* Python 3.10 or newer
* Bybit API key & secret (unified trading enabled)
* Telegram API ID & hash ([my.telegram.org](https://my.telegram.org))
* (Optional) CoinMarketCap API key

---

## 🛠️ Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/<your-username>/telegram-bybit-autotrader.git
   cd telegram-bybit-autotrader
   ```

2. **Create a virtual environment**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**

   * Copy the example file:

     ```bash
     cp config.env.example config.env
     ```
   * Open `config.env` and set your credentials.

---

## ⚙️ Configuration

Edit `config.env` with the following values:

```ini
# Telegram
TG_API_ID=<YOUR_TELEGRAM_API_ID>
TG_API_HASH=<YOUR_TELEGRAM_API_HASH>
TG_PHONE=<YOUR_TELEGRAM_PHONE_NUMBER>

# Bybit
BYBIT_API_KEY=<YOUR_BYBIT_API_KEY>
BYBIT_API_SECRET=<YOUR_BYBIT_API_SECRET>

# CoinMarketCap (optional)
CMC_API_KEY=<YOUR_CMC_API_KEY>
```

Adjust constants at the top of `bot.py` as needed:

* `INITIAL_TARGET_USDT`: Total USDT per announcement
* `TAKE_PROFIT_MULTIPLIER_FUTURES` / `SPOT`
* Market-cap thresholds and adjustment multipliers
* `COOLDOWN_PERIOD_SECONDS`
* `CHANNELS` list

---

## ▶️ Usage

Run the bot:

```bash
python bot.py
```

The bot will:

1. Connect to Telegram and Bybit.
2. Monitor specified channels for announcements.
3. Execute market buys and schedule post-buy take-profit/market-sell orders.

---

## 📂 Project Structure

```
├── bot.py             # Main script
├── config.env.example # Env var template
├── requirements.txt   # Dependencies
├── README.md          # This file
└── session_name/      # Telethon session data
```

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/YourFeature`)
3. Commit your changes (`git commit -m "Add YourFeature"`)
4. Push (`git push origin feature/YourFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
