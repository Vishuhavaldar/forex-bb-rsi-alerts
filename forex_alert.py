
import os
import json
import math
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

API_KEY = os.environ["7b68fb0cc966400aacbe9a67fa6362a5"]
BOT_TOKEN = os.environ["8958956370:AAG14a56M8rQS0g3gxoE1p_ozWL_de_nXtU"]
CHAT_ID = os.environ["1983276398"]

PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]

BB_PERIOD = 20
BB_STDDEV = 2
RSI_PERIOD = 14
STATE_FILE = "state.json"


def get_json(url, data=None):
    request = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": "ForexAlertBot/1.0"}
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_candles(pair):
    params = urllib.parse.urlencode({
        "symbol": pair,
        "interval": "15min",
        "outputsize": 100,
        "timezone": "UTC",
        "apikey": API_KEY
    })

    url = "https://api.twelvedata.com/time_series?" + params
    result = get_json(url)

    if result.get("status") == "error" or "values" not in result:
        raise RuntimeError(
            f"Market data error for {pair}: "
            f"{result.get('message', result)}"
        )

    candles = []

    for row in reversed(result["values"]):
        timestamp = datetime.fromisoformat(
            row["datetime"].replace("Z", "+00:00")
        )

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        candles.append({
            "time": timestamp.isoformat(),
            "timestamp": timestamp,
            "close": float(row["close"])
        })

    return candles


def calculate_bollinger_bands(closes):
    if len(closes) < BB_PERIOD:
        raise ValueError("Insufficient candles for Bollinger Bands")

    values = closes[-BB_PERIOD:]
    middle = sum(values) / BB_PERIOD

    variance = sum(
        (value - middle) ** 2 for value in values
    ) / BB_PERIOD

    deviation = math.sqrt(variance)

    upper = middle + BB_STDDEV * deviation
    lower = middle - BB_STDDEV * deviation

    return upper, middle, lower


def calculate_rsi(closes):
    if len(closes) <= RSI_PERIOD:
        raise ValueError("Insufficient candles for RSI")

    changes = [
        closes[i] - closes[i - 1]
        for i in range(1, len(closes))
    ]

    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]

    average_gain = sum(gains[:RSI_PERIOD]) / RSI_PERIOD
    average_loss = sum(losses[:RSI_PERIOD]) / RSI_PERIOD

    for i in range(RSI_PERIOD, len(changes)):
        average_gain = (
            average_gain * (RSI_PERIOD - 1) + gains[i]
        ) / RSI_PERIOD

        average_loss = (
            average_loss * (RSI_PERIOD - 1) + losses[i]
        ) / RSI_PERIOD

    if average_gain == 0 and average_loss == 0:
        return 50.0

    if average_loss == 0:
        return 100.0

    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def send_telegram(message):
    url = (
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    )

    payload = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message
    }).encode("utf-8")

    result = get_json(url, payload)

    if not result.get("ok"):
        raise RuntimeError(f"Telegram delivery failed: {result}")


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}


def save_state(state):
    temporary_file = STATE_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(state, file, indent=2)

    os.replace(temporary_file, STATE_FILE)


def check_pair(pair, state):
    candles = fetch_candles(pair)
    now = datetime.now(timezone.utc)

    # Ignore any candle that has not fully closed.
    completed = [
        candle for candle in candles
        if candle["timestamp"] + timedelta(minutes=15) <= now
    ]

    if len(completed) < max(BB_PERIOD, RSI_PERIOD + 1):
        raise RuntimeError(f"Not enough completed candles for {pair}")

    candle = completed[-1]
    candle_id = candle["time"]

    pair_state = state.setdefault(pair, {
        "last_candle": "",
        "armed": True
    })

    if pair_state["last_candle"] == candle_id:
        print(f"{pair}: candle already processed")
        return

    closes = [item["close"] for item in completed]

    close = closes[-1]
    upper, middle, lower = calculate_bollinger_bands(closes)
    rsi = calculate_rsi(closes)

    message = None

    # Re-arm only when a candle closes inside the bands.
    if lower <= close <= upper:
        pair_state["armed"] = True

    elif pair_state["armed"]:
        if close > upper and rsi >= 60:
            message = (
                f"🟢 UPPER BB BREAKOUT\n"
                f"Pair: {pair}\n"
                f"Timeframe: 15 minutes\n"
                f"Candle close (UTC): {candle_id}\n"
                f"Close: {close}\n"
                f"Upper BB: {upper}\n"
                f"RSI(14): {rsi:.2f}\n"
                f"Condition: Close > Upper BB and RSI >= 60"
            )

        elif close < lower and rsi <= 30:
            message = (
                f"🔴 LOWER BB BREAKOUT\n"
                f"Pair: {pair}\n"
                f"Timeframe: 15 minutes\n"
                f"Candle close (UTC): {candle_id}\n"
                f"Close: {close}\n"
                f"Lower BB: {lower}\n"
                f"RSI(14): {rsi:.2f}\n"
                f"Condition: Close < Lower BB and RSI <= 30"
            )

    if message:
        # Only disarm after Telegram confirms delivery.
        send_telegram(message)
        pair_state["armed"] = False
        print(f"{pair}: Telegram alert sent")
    else:
        print(
            f"{pair}: no alert | close={close} "
            f"upper={upper} lower={lower} RSI={rsi:.2f}"
        )

    pair_state["last_candle"] = candle_id


def main():
    state = load_state()

    for pair in PAIRS:
        try:
            check_pair(pair, state)
        except Exception as error:
            print(f"ERROR [{pair}]: {error}")
        finally:
            # Preserve successful results even if another pair fails.
            save_state(state)


if __name__ == "__main__":
    main()
