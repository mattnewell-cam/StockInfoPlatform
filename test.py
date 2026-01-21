# Turnover vs Market Cap (S&P 500 random 100) using yfinance
# pip install yfinance pandas numpy matplotlib lxml

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

# --- Pull current S&P 500 constituents from Wikipedia ---
sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
tickers = pd.read_html(sp500_url)[0]["Symbol"].tolist()

# Yahoo Finance ticker quirks: BRK.B -> BRK-B, BF.B -> BF-B, dots -> dashes
def yf_ticker(t: str) -> str:
    return t.replace(".", "-")

tickers = [yf_ticker(t) for t in tickers]

# --- Random sample of 100 ---
rng = np.random.default_rng(42)
sample = rng.choice(tickers, size=100, replace=False).tolist()

# --- Download last 6 months daily volumes/prices in one go (faster than per-ticker) ---
# If you hit rate limits, set threads=False or chunk the tickers into batches of 25.
px = yf.download(
    tickers=sample,
    period="6mo",
    interval="1d",
    auto_adjust=False,
    group_by="ticker",
    threads=True,
    progress=False,
)

# Compute 6mo average daily volume per ticker
avg_vol = {}
last_price = {}

for t in sample:
    # yfinance returns either MultiIndex columns or single-index if one ticker; handle both
    if isinstance(px.columns, pd.MultiIndex):
        vol = px[(t, "Volume")].dropna()
        close = px[(t, "Close")].dropna()
    else:
        # single ticker case fallback
        vol = px["Volume"].dropna()
        close = px["Close"].dropna()

    if len(vol) == 0 or len(close) == 0:
        continue

    avg_vol[t] = float(vol.mean())
    last_price[t] = float(close.iloc[-1])

# --- Get market cap + shares outstanding (fast_info first, then fallbacks) ---
rows = []
for t in sample:
    if t not in avg_vol:
        continue

    tk = yf.Ticker(t)

    mcap = None
    shares = None

    # fast_info is much quicker than info (and less rate-limit prone)
    try:
        fi = tk.fast_info
        # keys vary by yfinance version; try a few
        mcap = fi.get("market_cap") or fi.get("marketCap")
        shares = fi.get("shares") or fi.get("shares_outstanding") or fi.get("sharesOutstanding")
        price = fi.get("last_price") or fi.get("lastPrice") or last_price.get(t)
    except Exception:
        fi = {}
        price = last_price.get(t)

    # Fallback: compute shares from mcap/price if shares missing
    if shares is None and mcap is not None and price:
        shares = mcap / price

    # Slow fallback: tk.info (only if still missing critical fields)
    if mcap is None or shares is None:
        try:
            info = tk.get_info()
            mcap = mcap or info.get("marketCap")
            shares = shares or info.get("sharesOutstanding")
        except Exception:
            pass

    if mcap is None or shares is None or shares == 0:
        continue

    # Turnover proxy: annualised share turnover using 6mo avg daily volume
    # (avg daily volume * 252 trading days) / shares outstanding
    turnover = (avg_vol[t] * 252.0) / shares

    rows.append({
        "ticker": t,
        "market_cap": float(mcap),
        "shares_outstanding": float(shares),
        "avg_daily_volume_6mo": float(avg_vol[t]),
        "turnover_annualised": float(turnover),
    })

df = pd.DataFrame(rows).dropna()

print(f"Sample size after missing-data drops: {len(df)}")
print(df[["market_cap", "turnover_annualised"]].describe())

# --- Correlations (use log market cap; turnover is already scale-free) ---
df["log_mcap"] = np.log10(df["market_cap"])
pearson = df["log_mcap"].corr(df["turnover_annualised"], method="pearson")
spearman = df["log_mcap"].corr(df["turnover_annualised"], method="spearman")

print(f"Pearson corr(log10 mcap, turnover):  {pearson:.3f}")
print(f"Spearman corr(log10 mcap, turnover): {spearman:.3f}")

# --- Plot ---
plt.figure(figsize=(9, 6))
plt.scatter(df["market_cap"], df["turnover_annualised"])
plt.xscale("log")
plt.yscale("log")
plt.xlabel("Market cap (log scale)")
plt.ylabel("Annualised turnover proxy (log scale)")
plt.title("S&P 500 (random 100): turnover vs market cap (yfinance)")

# Optional trendline on log-log axes
x = np.log10(df["market_cap"].values)
y = np.log10(df["turnover_annualised"].values)
coef = np.polyfit(x, y, 1)  # slope, intercept
x_line = np.linspace(x.min(), x.max(), 100)
y_line = coef[0] * x_line + coef[1]
plt.plot(10**x_line, 10**y_line)

plt.tight_layout()
plt.show()
