# bot.py (filtered version)
import requests
import time
import datetime
from collections import deque
import statistics

# ===========================
# === USER CONFIG ===========
# ===========================
TELEGRAM_TOKEN = "8333823268:AAFN3UeLWQrr1lCeT8oG5d3CU6UKFB1FCg8"
CHAT_ID = "8410854765"
PAIRS = ["BTC", "ETH", "SOL", "BNB"]

SAMPLE_INTERVAL = 60
WINDOW_5 = 5
WINDOW_60 = 60

MIN_CONFIDENCE = 85
TRADE_HISTORY = {p: deque(maxlen=10) for p in PAIRS}
LAST_SIGNAL_TIME = {p: 0 for p in PAIRS}

VOL_FILTER = {"BTC": 15, "ETH": 2, "SOL": 0.5, "BNB": 0.3}

# ===========================
# === TELEGRAM ==============
# ===========================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}
    try:
        requests.post(url, data=payload, timeout=8)
    except:
        pass

# ===========================
# === PRICE & ORDERBOOK =====
# ===========================
def get_price(pair):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={pair}USDT"
        r = requests.get(url, timeout=6)
        return float(r.json()["price"])
    except:
        return None

def get_orderbook(pair):
    try:
        url = f"https://api.binance.com/api/v3/depth?symbol={pair}USDT&limit=50"
        r = requests.get(url, timeout=6).json()
        bids = sum(float(b[1]) for b in r.get("bids", []))
        asks = sum(float(a[1]) for a in r.get("asks", []))
        if bids > asks * 1.2:
            return "Buy"
        elif asks > bids * 1.2:
            return "Sell"
        return "Neutral"
    except:
        return None

# ===========================
# === SL/TP & RR ============
# ===========================
def compute_sl_tp(entry, vol, direction):
    sl_dist = max(vol * 1.5, entry * 0.0005)
    if direction == "LONG":
        sl = entry - sl_dist
        tp1 = entry + sl_dist * 1.5
    else:
        sl = entry + sl_dist
        tp1 = entry - sl_dist * 1.5
    rr = abs((tp1 - entry) / (entry - sl)) if entry != sl else 0
    return round(sl, 2), round(tp1, 2), round(rr, 2)

# ===========================
# === SIGNAL BUILDER ========
# ===========================
def build_signal(pair, win5, win60):
    price = get_price(pair)
    if not price: return None
    if len(win5) < 2: return None

    avg5 = sum(win5) / len(win5)
    avg60 = sum(win60) / len(win60) if win60 else avg5
    direction = "LONG" if price > avg5 else "SHORT"
    vol = statistics.pstdev(win5) if len(win5) > 1 else 0
    sl, tp1, rr = compute_sl_tp(price, vol, direction)
    orderbook = get_orderbook(pair)

    # --- FILTERS ---
    if orderbook == "Buy" and direction != "LONG": return None
    if orderbook == "Sell" and direction != "SHORT": return None
    if (direction == "LONG" and avg60 > avg5) or (direction == "SHORT" and avg60 < avg5):
        return None
    if vol < VOL_FILTER[pair]: return None
    if rr < 1.5: return None

    # history filter
    wins = TRADE_HISTORY[pair].count("✅")
    if len(TRADE_HISTORY[pair]) >= 5 and wins / len(TRADE_HISTORY[pair]) < 0.5:
        return None

    confidence = 85
    now = time.time()
    if now - LAST_SIGNAL_TIME[pair] < 600:  # avoid overtrading (10 min)
        return None
    LAST_SIGNAL_TIME[pair] = now

    return {
        "pair": pair, "price": price, "dir": direction,
        "sl": sl, "tp1": tp1, "rr": rr,
        "vol": vol, "conf": confidence,
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

# ===========================
# === MAIN LOOP =============
# ===========================
def main():
    win5, win60 = {p: [] for p in PAIRS}, {p: [] for p in PAIRS}
    while True:
        signals = []
        for pair in PAIRS:
            price = get_price(pair)
            if not price: continue
            win5[pair].append(price); win60[pair].append(price)
            if len(win5[pair]) > WINDOW_5: win5[pair].pop(0)
            if len(win60[pair]) > WINDOW_60: win60[pair].pop(0)
            sig = build_signal(pair, win5[pair], win60[pair])
            if sig: signals.append(sig)

        for s in signals:
            msg = (
                f"📊 FILTERED SIGNAL\n\n"
                f"Pair: {s['pair']}/USDT\n"
                f"Time: {s['time']}\n"
                f"Direction: {s['dir']}\n"
                f"Entry: {s['price']}\n"
                f"Stop Loss: {s['sl']}\n"
                f"TP1: {s['tp1']}\n"
                f"RR: {s['rr']}\n"
                f"Volatility: {round(s['vol'],3)}\n"
                f"Confidence: {s['conf']}%"
            )
            print("[ALERT]", msg)
            send_telegram(msg)
        time.sleep(SAMPLE_INTERVAL)

if __name__ == "__main__":
    main()
