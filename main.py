import os
import logging
import re
from decimal import Decimal as D, ROUND_DOWN, ROUND_UP
from telethon import TelegramClient, events
from pybit.unified_trading import HTTP
from dotenv import load_dotenv
import requests
import asyncio
from datetime import datetime, timedelta

# Load environment variables
load_dotenv('config.env')

# Telegram client setup
TG_API_ID = int(os.getenv('TG_API_ID'))
TG_API_HASH = os.getenv('TG_API_HASH')
TG_PHONE = os.getenv('TG_PHONE')
CHANNELS = [-1001124574831]  # Channels to monitor

# Bybit and CoinMarketCap credentials
BYBIT_API_KEY = os.getenv('BYBIT_API_KEY')
BYBIT_API_SECRET = os.getenv('BYBIT_API_SECRET')
CMC_API_KEY = ''
COINGECKO_API_KEY = ''

# Adjustable constants
INITIAL_TARGET_USDT = D("600")
TAKE_PROFIT_MULTIPLIER_FUTURES = D("1.45")
TAKE_PROFIT_MULTIPLIER_SPOT = D("3")

INCREASE_MULTIPLIER_ADJUSTMENT_FUTURES = D("0.3")  # For "futures will launch"
DECREASE_MULTIPLIER_ADJUSTMENT_FUTURES = D("0.2")  # For "futures will launch"
INCREASE_MULTIPLIER_ADJUSTMENT_SPOT = D("4")  # For "will list"
DECREASE_MULTIPLIER_ADJUSTMENT_SPOT = D("1.5")  # For "will list"

# Market cap thresholds
FUTURES_ULTRALOW_MC = D("100000000")  # Skip take-profit order if below this
FUTURES_LOW_MC = D("150000000")  # Increase multiplier if between ULTRALOW and LOW
FUTURES_MID_MC = D("180000000")  # Decrease multiplier if between MID and MAX
FUTURES_MAX_MC = D("250000000")  # Market sell if above MAX
SPOT_MC_THRESHOLD = D("150000000")  # Lower threshold for "will list" scenario
SPOT_MC_THRESHOLD2 = D("500000000")  # Upper threshold for "will list" scenario

# Cooldown configuration
COOLDOWN_PERIOD_SECONDS = 60  # Cooldown period between market buy orders
last_buy_time = {}

# Initialize Telegram client
client = TelegramClient('session_name', TG_API_ID, TG_API_HASH, sequential_updates=False)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("telethon").setLevel(logging.WARNING)

# Initialize Bybit session
session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET, testnet=False)

# Function to get market cap from CoinMarketCap
def get_market_cap_from_cmc(symbol):
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': CMC_API_KEY,
    }
    parameters = {'symbol': symbol, 'convert': 'USD'}
    try:
        response = requests.get(url, headers=headers, params=parameters)
        if response.status_code == 200:
            data = response.json()
            return D(data['data'][symbol]['quote']['USD']['market_cap'])
        else:
            logger.error(f"Error fetching market cap from CMC: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error retrieving market cap from CMC for {symbol}: {e}")
        return None

# Function to get market cap from CoinGecko
def get_market_cap_from_coingecko(symbol, coin_list):
    try:
        # Find the CoinGecko ID for the given symbol
        coin_id = next((coin['id'] for coin in coin_list if coin['symbol'].lower() == symbol.lower()), None)
        if not coin_id:
            logger.error(f"CoinGecko ID for {symbol} not found.")
            return None

        # Fetch market cap using the CoinGecko ID
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return D(data['market_data']['market_cap']['usd'])
        else:
            logger.error(f"Error fetching market cap from CoinGecko: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error fetching market cap from CoinGecko: {e}")
        return None

# Function to get the full list of coins from CoinGecko
def get_coingecko_coin_list():
    try:
        url = "https://api.coingecko.com/api/v3/coins/list"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Error fetching CoinGecko coin list: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error fetching CoinGecko coin list: {e}")
        return None

# Function to clean up ticker by removing numbers divisible by 10 and "1M" prefix
def clean_ticker(ticker):
    if ticker.startswith("1M"):
        ticker = ticker[2:]
    match = re.match(r'^(\d+)(\w+)', ticker)
    if match:
        number = int(match.group(1))
        if number % 10 == 0:
            ticker = match.group(2)
    return ticker

# Function to execute market buy order with cooldown
async def execute_market_buy_order(ticker, target_usdt_value):
    global last_buy_time
    current_time = datetime.now()

    # Check if there is a cooldown in place for the ticker
    if ticker in last_buy_time:
        elapsed_time = (current_time - last_buy_time[ticker]).total_seconds()
        if elapsed_time < COOLDOWN_PERIOD_SECONDS:
            logger.info(f"Cooldown in effect for {ticker}. Skipping market buy.")
            return False

    try:
        buy_order_time = datetime.now()  # Record the time when the buy order is executed
        logger.info(f"Executing market buy order for {ticker} at {buy_order_time.strftime('%H:%M:%S:%f')}")
        buy_order_response = session.place_order(
            category='spot', symbol=ticker, side='Buy', orderType='Market',
            qty=str(target_usdt_value), timeInForce='IOC'
        )
        if buy_order_response['retCode'] == 0:
            logger.info(f"Market buy order placed successfully: {buy_order_response}")
            last_buy_time[ticker] = current_time  # Update the last buy time
            return True
        else:
            logger.error(f"Failed to place market buy order: {buy_order_response['retMsg']}")
            return False
    except Exception as e:
        logger.error(f"Error placing market buy order for {ticker}: {e}")
        return False

# Function to perform post-buy operations
async def post_buy_operations(ticker, message_type):
    await asyncio.sleep(5)
    base_currency = ticker.replace("USDT", "")
    logger.info(f"Starting post-buy operations for {ticker} ({base_currency})")

    # Step 1: Retrieve account balance
    balance_response = session.get_wallet_balance(accountType='UNIFIED')
    if balance_response['retCode'] != 0:
        logger.error(f"Failed to retrieve account balance: {balance_response['retMsg']}")
        return

    coins = balance_response['result']['list'][0]['coin']
    token_balance = next((item for item in coins if item['coin'] == base_currency), None)
    if not token_balance:
        logger.error(f"Failed to retrieve balance for {base_currency}")
        return

    # Step 2: Round the quantity to two decimals initially
    qty = D(token_balance['walletBalance']).quantize(D("1.00"), rounding=ROUND_DOWN)
    if qty <= 0:
        logger.error(f"Quantity for {ticker} is zero or less, cannot proceed with sell order.")
        return
    logger.info(f"Retrieved balance for {base_currency}: {qty}")

    # Step 3: Fetch market cap from CMC, then fallback to CoinGecko if needed
    market_cap = get_market_cap_from_cmc(base_currency)
    if market_cap is None or market_cap == 0:
        logger.info("Market cap from CMC is zero or unavailable. Trying CoinGecko...")
        coin_list = get_coingecko_coin_list()
        if coin_list:
            market_cap = get_market_cap_from_coingecko(base_currency, coin_list)
        if market_cap is None:
            logger.error("Failed to retrieve market cap from both CMC and CoinGecko.")
            return
    logger.info(f"Current market cap of {base_currency}: {market_cap}")

    # Step 4: Determine the appropriate multiplier and action based on market cap
    take_profit_multiplier = (
        TAKE_PROFIT_MULTIPLIER_FUTURES if message_type == "futures will launch" else TAKE_PROFIT_MULTIPLIER_SPOT
    )

    if message_type == "futures will launch":
        if market_cap < FUTURES_ULTRALOW_MC:
            logger.info("Market cap is below FUTURES_ULTRALOW_MC. Skipping take-profit order.")
            return
        elif FUTURES_ULTRALOW_MC < market_cap < FUTURES_LOW_MC:
            logger.info(f"Market cap is between {FUTURES_ULTRALOW_MC} and {FUTURES_LOW_MC}. Increasing multiplier.")
            take_profit_multiplier += INCREASE_MULTIPLIER_ADJUSTMENT_FUTURES
        elif FUTURES_MID_MC < market_cap < FUTURES_MAX_MC:
            logger.info(f"Market cap is between {FUTURES_MID_MC} and {FUTURES_MAX_MC}. Decreasing multiplier.")
            take_profit_multiplier -= DECREASE_MULTIPLIER_ADJUSTMENT_FUTURES
        elif market_cap >= FUTURES_MAX_MC:
            logger.info(f"Market cap is above {FUTURES_MAX_MC}. Executing market sell.")
            await place_order_with_quantity_adjustment(ticker, qty, None, "Market", "Sell", "IOC")
            return

    elif message_type == "will list":
        if market_cap <= SPOT_MC_THRESHOLD:
            logger.info(f"Market cap is below or equal to {SPOT_MC_THRESHOLD}. Increasing multiplier.")
            take_profit_multiplier += INCREASE_MULTIPLIER_ADJUSTMENT_SPOT
        elif SPOT_MC_THRESHOLD < market_cap < SPOT_MC_THRESHOLD2:
            logger.info("Market cap is within the stable range. No changes to take profit.")
        elif market_cap >= SPOT_MC_THRESHOLD2:
            logger.info(f"Market cap is above or equal to {SPOT_MC_THRESHOLD2}. Decreasing multiplier.")
            take_profit_multiplier -= DECREASE_MULTIPLIER_ADJUSTMENT_SPOT

    # Step 5: Fetch kline data for price calculations
    end_time = int((datetime.now() - timedelta(seconds=30)).timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(seconds=180)).timestamp() * 1000)
    kline_response = session.get_kline(category='spot', symbol=ticker, interval='1', start=start_time, end=end_time, limit=100)
    if kline_response['retCode'] != 0 or not kline_response['result']['list']:
        logger.error("Failed to fetch kline data.")
        return

    closing_prices = [D(candle[4]) for candle in kline_response['result']['list']]
    average_price = sum(closing_prices) / len(closing_prices)
    max_decimals = max(len(str(price).split('.')[1]) for price in closing_prices)
    decimal_format = f"1.{'0' * max_decimals}"
    logger.info(f"Calculated average price: {average_price}")

    # Step 6: Calculate final take-profit price
    take_profit_price = (average_price * take_profit_multiplier).quantize(D(decimal_format), rounding=ROUND_UP)
    logger.info(f"Calculated take-profit price: {take_profit_price}")

    # Step 7: Place limit sell order with delay and retry logic
    await asyncio.sleep(2)
    await place_order_with_quantity_adjustment(ticker, qty, take_profit_price, "Limit", "Sell", "GTC")

# Function to place an order with quantity adjustment
async def place_order_with_quantity_adjustment(ticker, qty, price, order_type, side, time_in_force):
    try:
        qty_str = str(qty)
        logger.info(f"Attempting to place {side} order with qty: {qty_str}")
        order_response = session.place_order(
            category='spot', symbol=ticker, side=side, orderType=order_type,
            qty=qty_str, price=str(price) if price else None, timeInForce=time_in_force
        )
        if order_response['retCode'] == 0:
            logger.info(f"{side} order placed successfully: {order_response}")
        elif "too many decimals" in order_response.get('retMsg', '').lower():
            logger.warning("Order quantity has too many decimals. Rounding quantity and retrying...")
            qty = qty.quantize(D("1"), rounding=ROUND_DOWN)
            qty_str = str(qty)
            logger.info(f"Retrying with rounded quantity: {qty_str}")
            order_response = session.place_order(
                category='spot', symbol=ticker, side=side, orderType=order_type,
                qty=qty_str, price=str(price) if price else None, timeInForce=time_in_force
            )
            if order_response['retCode'] == 0:
                logger.info(f"{side} order placed successfully after adjustment: {order_response}")
            else:
                logger.error(f"Failed to place {side} order after adjustment: {order_response['retMsg']}")
        else:
            logger.error(f"Failed to place {side} order: {order_response['retMsg']}")
    except Exception as e:
        logger.error(f"Exception during order placement: {e}")

# Telegram message handler
async def handle_new_message(event):
    if event.chat_id not in CHANNELS:
        return

    message = event.message.message
    tickers, message_type = [], None

    if "futures will launch" in message.lower():
        message_type = "futures will launch"
        tickers = [clean_ticker(ticker) for ticker in re.findall(r'\b(\w+USDT)\b', message)]
    elif "will list" in message.lower():
        message_type = "will list"
        tickers = [clean_ticker(symbol + "USDT") for symbol in re.findall(r'\((\w+)\)', message)]

    if tickers:
        usdt_per_ticker = INITIAL_TARGET_USDT / D(len(tickers))

        # Phase 1: Market Buy Orders
        successful_buys = []
        for ticker in tickers:
            if await execute_market_buy_order(ticker, usdt_per_ticker):
                successful_buys.append((ticker, message_type))  # Collect successful buys

        # Phase 2: Post-Buy Operations
        for ticker, msg_type in successful_buys:
            await post_buy_operations(ticker, msg_type)

# Run the bot
async def run_bot():
    while True:
        try:
            await client.start(phone=TG_PHONE)
            @client.on(events.NewMessage(chats=CHANNELS))
            async def handler(event):
                await handle_new_message(event)
            logger.info("Bot is running. Waiting for messages...")
            await client.run_until_disconnected()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error: {e}. Restarting in 30 seconds...")
            await asyncio.sleep(30)

if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Script interrupted.")
