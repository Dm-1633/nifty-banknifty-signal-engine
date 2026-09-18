import os, requests, datetime as dt
import pandas as pd, numpy as np
import streamlit as st
import plotly.graph_objects as go
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands

st.set_page_config(page_title="NIFTY Signal Engine", page_icon="📈", layout="wide")

TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
BASE = "https://api.upstox.com"
INDICES = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "INDIA VIX": "NSE_INDEX|India VIX"
}

def headers():
    return {"Accept":"application/json","Authorization":f"Bearer {TOKEN}"}

@st.cache_data(ttl=20)
def live_candles(key, minutes=5):
    if not TOKEN: return pd.DataFrame()
    url=f"{BASE}/v3/historical-candle/intraday/{key}/minutes/{minutes}"
    r=requests.get(url, headers=headers(), timeout=10)
    r.raise_for_status()
    c=r.json()["data"]["candles"]
    if not c: return pd.DataFrame()
    df=pd.DataFrame(c, columns=["time","Open","High","Low","Close","Volume","OI"])
    df["time"]=pd.to_datetime(df["time"])
    return df.sort_values("time").set_index("time")

@st.cache_data(ttl=300)
def history(key, minutes=5, days=30):
    if not TOKEN: return pd.DataFrame()
    end=dt.date.today()
    start=end-dt.timedelta(days=days)
    url=f"{BASE}/v3/historical-candle/{key}/minutes/{minutes}/{end}/{start}"
    r=requests.get(url, headers=headers(), timeout=15)
    r.raise_for_status()
    c=r.json()["data"]["candles"]
    df=pd.DataFrame(c, columns=["time","Open","High","Low","Close","Volume","OI"])
    df["time"]=pd.to_datetime(df["time"])
    return df.sort_values("time").set_index("time")

@st.cache_data(ttl=30)
def quote(keys):
    if not TOKEN: return {}
    r=requests.get(f"{BASE}/v2/market-quote/quotes",
                   params={"instrument_key":",".join(keys)},
                   headers=headers(), timeout=10)
    r.raise_for_status()
    return r.json().get("data",{})

@st.cache_data(ttl=30)
def option_chain(key, expiry="current_week"):
    if not TOKEN: return pd.DataFrame()
    r=requests.get(f"{BASE}/v2/option/chain",
                   params={"instrument_key":key,"expiry_date":expiry},
                   headers=headers(), timeout=12)
    r.raise_for_status()
    data=r.json().get("data",[])
    rows=[]
    for z in data:
        call=z.get("call_options",{})
        put=z.get("put_options",{})
        cm=call.get("market_data",{})
        pm=put.get("market_data",{})
        rows.append({
            "strike":z.get("strike_price"),
            "call_oi":cm.get("oi",0),"call_prev_oi":cm.get("prev_oi",0),
            "call_ltp":cm.get("ltp",0),"call_vol":cm.get("volume",0),
            "put_oi":pm.get("oi",0),"put_prev_oi":pm.get("prev_oi",0),
            "put_ltp":pm.get("ltp",0),"put_vol":pm.get("volume",0),
            "pcr":z.get("pcr")
        })
    return pd.DataFrame(rows)

def indicators(x):
    x=x.copy()
    x["EMA20"]=EMAIndicator(x.Close,20).ema_indicator()
    x["EMA50"]=EMAIndicator(x.Close,50).ema_indicator()
    x["RSI"]=RSIIndicator(x.Close,14).rsi()
    m=MACD(x.Close,26,12,9); x["MACD"]=m.macd(); x["MACD_SIGNAL"]=m.macd_signal()
    x["ADX"]=ADXIndicator(x.High,x.Low,x.Close,14).adx()
    x["ATR"]=AverageTrueRange(x.High,x.Low,x.Close,14).average_true_range()
    b=BollingerBands(x.Close,20,2); x["BB_H"]=b.bollinger_hband(); x["BB_L"]=b.bollinger_lband()
    tp=(x.High+x.Low+x.Close)/3
    v=x.Volume.replace(0,np.nan)
    x["VWAP"]=(tp*v).cumsum()/v.cumsum()
    x["VOL_MA20"]=x.Volume.rolling(20).mean()
    x["RET"]=x.Close.pct_change()
    return x.dropna()

def signal(r, option_df=None, vix=None):
    s=0; reasons=[]
    def add(points, typ, msg):
        nonlocal s
        s+=points; reasons.append((typ,msg))
    add(18,"Bullish","EMA20 > EMA50") if r.EMA20>r.EMA50 else add(-18,"Bearish","EMA20 < EMA50")
    add(15,"Bullish","Price above VWAP") if r.Close>r.VWAP else add(-15,"Bearish","Price below VWAP")
    if 55<=r.RSI<72: add(12,"Bullish",f"RSI {r.RSI:.1f} supports momentum")
    elif 28<r.RSI<=45: add(-12,"Bearish",f"RSI {r.RSI:.1f} supports downside momentum")
    if r.MACD>r.MACD_SIGNAL: add(12,"Bullish","MACD above signal")
    else: add(-12,"Bearish","MACD below signal")
    if r.ADX>=20: add(10 if r.EMA20>r.EMA50 else -10,"Bullish" if r.EMA20>r.EMA50 else "Bearish",f"ADX {r.ADX:.1f} confirms trend strength")
    else: reasons.append(("Neutral",f"ADX {r.ADX:.1f}: weak trend"))
    if r.Volume>r.VOL_MA20: add(8 if r.RET>=0 else -8,"Bullish" if r.RET>=0 else "Bearish","Above-average volume confirmation")
    if option_df is not None and not option_df.empty:
        total_call=option_df.call_oi.sum(); total_put=option_df.put_oi.sum()
        pcr=(total_put/total_call) if total_call else np.nan
        if pd.notna(pcr):
            if pcr>=1.05: add(10,"Bullish",f"Option-chain PCR {pcr:.2f}")
            elif pcr<=0.85: add(-10,"Bearish",f"Option-chain PCR {pcr:.2f}")
            else: reasons.append(("Neutral",f"Option-chain PCR {pcr:.2f}"))
    if vix is not None:
        reasons.append(("Context",f"India VIX {vix:,.2f}"))
    s=int(max(-100,min(100,s)))
    action="BUY" if s>=45 else ("SELL" if s<=-45 else "WAIT")
    conf=min(99,50+abs(s)//2)
    return action,s,conf,reasons

st.markdown("""<style>
.block-container{padding-top:1rem;max-width:1400px}
[data-testid="stMetricValue"]{font-size:1.7rem}
@media(max-width:700px){.block-container{padding:0.6rem}.stMetric{padding:.2rem}}
</style>""", unsafe_allow_html=True)

st.title("📈 NIFTY / BANKNIFTY Signal Engine")
st.caption("Tablet-ready research dashboard • Live mode requires a market-data API token")

with st.sidebar:
    st.header("Settings")
    index=st.selectbox("Index",["NIFTY","BANKNIFTY"])
    mins=st.selectbox("Candle", [1,3,5,15,30], index=2)
    expiry=st.selectbox("Options expiry",["current_week","next_week","current_month"])
    if st.button("🔄 Refresh"):
        st.cache_data.clear(); st.rerun()

if not TOKEN:
    st.warning("Live API is not connected yet. Set UPSTOX_ACCESS_TOKEN in your hosting platform's secrets/environment variables.")
    st.info("The app is intentionally shipped without any API secret. Never put a broker token directly into the source code.")
    st.stop()

key=INDICES[index]
df=live_candles(key,mins)
if len(df)<60:
    st.error("Not enough live candles returned. Try a larger interval or check your API access.")
    st.stop()

x=indicators(df)
opt=option_chain(key,expiry)
q=quote([key,INDICES["INDIA VIX"]])
vix=None
for val in q.values():
    if isinstance(val,dict) and "last_price" in val:
        vix=val["last_price"] if vix is None else vix

r=x.iloc[-1]
action,score,conf,reasons=signal(r,opt,vix)

a,b,c,d,e=st.columns(5)
a.metric("Price",f"{r.Close:,.2f}")
b.metric("Signal",action)
c.metric("Score",f"{score}/100")
d.metric("Confidence",f"{conf}%")
e.metric("RSI",f"{r.RSI:.1f}")

if action=="BUY": st.success("🟢 BUY setup detected")
elif action=="SELL": st.error("🔴 SELL setup detected")
else: st.warning("🟡 WAIT — factors are not sufficiently aligned")

l,rcol=st.columns([2,1])
with l:
    fig=go.Figure(go.Candlestick(x=x.index,open=x.Open,high=x.High,low=x.Low,close=x.Close,name=index))
    for col in ["EMA20","EMA50","VWAP"]:
        fig.add_trace(go.Scatter(x=x.index,y=x[col],name=col))
    fig.update_layout(height=520,xaxis_rangeslider_visible=False,margin=dict(l=5,r=5,t=20,b=5))
    st.plotly_chart(fig,use_container_width=True)
with rcol:
    st.subheader("Why?")
    for typ,msg in reasons:
        icon={"Bullish":"🟢","Bearish":"🔴","Neutral":"🟡","Context":"🔵"}.get(typ,"•")
        st.write(f"{icon} **{msg}**")
    st.subheader("Risk context")
    st.write(f"ATR: **{r.ATR:,.2f}**")
    st.write(f"ADX: **{r.ADX:.1f}**")
    st.write(f"VWAP: **{r.VWAP:,.2f}**")

if not opt.empty:
    st.subheader("Option-chain summary")
    total_call=opt.call_oi.sum(); total_put=opt.put_oi.sum()
    pcr=total_put/total_call if total_call else np.nan
    oi1,oi2,oi3=st.columns(3)
    oi1.metric("Call OI",f"{total_call:,.0f}")
    oi2.metric("Put OI",f"{total_put:,.0f}")
    oi3.metric("PCR",f"{pcr:.2f}" if pd.notna(pcr) else "—")
    st.dataframe(opt,use_container_width=True,height=300)

st.subheader("Latest indicator values")
st.dataframe(x[["Open","High","Low","Close","Volume","EMA20","EMA50","RSI","MACD","ADX","ATR","VWAP"]].tail(20),use_container_width=True)

st.caption("This is an analytical/paper-trading tool. A BUY/SELL label is not a guarantee of profit. Validate the strategy with walk-forward testing and realistic costs/slippage before using real capital.")
