
import os
import json
import urllib.request
import urllib.parse

params = urllib.parse.urlencode({
    "symbol": "ETH/USD",
    "interval": "1min",
    "outputsize": 5,
    "apikey": os.environ["7b68fb0cc966400aacbe9a67fa6362a5"]
})

url = f"https://api.twelvedata.com/time_series?{params}"

try:
    with urllib.request.urlopen(url, timeout=20) as response:
        result = json.loads(response.read().decode())

    if result.get("status") == "error":
        print("FAIL: Twelve Data returned an API error.")
        print(result.get("message", "Unknown API error"))

    elif result.get("values"):
        print("PASS: Candle data received.")
        print("Symbol:", result.get("meta", {}).get("symbol"))
        print("Interval:", result.get("meta", {}).get("interval"))
        print("Number of candles:", len(result["values"]))
        print("Latest returned candle:", result["values"][0])

    else:
        print("FAIL: No candle values returned.")
        print(result)

except Exception as error:
    print("FAIL: Data request failed.")
    print(type(error).__name__, str(error))
