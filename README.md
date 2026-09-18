# Tablet-ready NIFTY / BANKNIFTY Signal Engine

This version is designed to run as a cloud-hosted Streamlit web app. Open the URL from any tablet/phone/laptop browser.

## Live data
The app supports an Upstox access token through the environment variable `UPSTOX_ACCESS_TOKEN`. It uses the documented Upstox market-data, historical-candle and option-chain APIs.

## Deploy
1. Create a GitHub repository and upload these files.
2. Deploy the repository on Streamlit Community Cloud, or use Docker on a cloud host.
3. Add `UPSTOX_ACCESS_TOKEN` as a secret/environment variable.
4. Open the generated HTTPS URL on your tablet.
5. Add the URL to your tablet home screen for an app-like experience.

## Security
Never commit the access token to GitHub. Use the hosting platform's Secrets/Environment Variables.

## Current features
- Responsive tablet UI
- NIFTY and BANKNIFTY
- Live intraday candles
- EMA20/50, RSI, MACD, ADX, ATR, VWAP, volume
- Transparent BUY/SELL/WAIT scoring
- Option-chain OI/PCR when API access is available
- India VIX context
- Candlestick dashboard

## Planned production additions
Futures OI, change-in-OI classification, FII/DII, market breadth, support/resistance, multi-timeframe confirmation, signal history, alerts, walk-forward backtesting, and broker execution only after validation.
