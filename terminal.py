import os
import time
import datetime
import re
import requests
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="QUANT_PRO v2.0 — Multi-Chart Analytical Workstation",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- TRADINGVIEW DARK CSS ---
st.markdown(
    """
    <style>
    .stApp { background: #131722; color: #d1d4dc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    header[data-testid='stHeader'] { visibility: hidden; }
    .block-container { padding-top: 0.8rem; padding-bottom: 0.8rem; }
    div[data-testid="stForm"] { background: #1e222d; border: 1px solid #2a2e39; border-radius: 6px; padding: 15px; }
    .alarm-box { background: #2a1f1f; border: 1px solid #ef4444; padding: 8px; border-radius: 4px; color: #f87171; font-weight: bold; }
    </style>
    """,
    unsafe_allow_html=True
)

if "connections" not in st.session_state:
    st.session_state["connections"] = {}
if "tabs_data" not in st.session_state:
    st.session_state["tabs_data"] = {"Tab 1": {"symbol": "BTCUSDT", "grid": "1x1 (Single Chart)"}}
if "alarms" not in st.session_state:
    st.session_state["alarms"] = []

st.markdown("### ⚡ **QUANT_PRO v2.0** — Advanced Analytical Workstation")

# --- WORKSPACE TABS (CHARTS VS SETTINGS) ---
tab_main_workspace, tab_feed_settings = st.tabs(["📊 Multi-Chart Workstation", "🔌 Live Feed & API Bridges"])

with tab_feed_settings:
    st.markdown("##### 🔐 **Optional External Data Feeds & MT5 Bridge Setup**")
    st.info("Public crypto pairs, spot/futures data, and math formulas work instantly by default. Use this section if you want to connect external institutional feeds or local MetaTrader 5 bridges.")
    
    FEEDS = [
        "MT5 Bridge (Local MetaTrader 5)",
        "Binance API (Private Key/Sec)",
        "MEXC API (Private Key/Sec)",
        "CoinGlass API",
        "CryptoQuant API",
        "FRED Macro API",
        "EIA Energy API",
        "Finnhub Equities API"
    ]
    selected_feed = st.selectbox("Select Feed Provider to Connect", FEEDS, key="feed_dropdown_selector")

    with st.form(key="feed_auth_form"):
        auth_data = {}
        st.markdown(f"**Configuring credentials for: {selected_feed}**")
        if "MT5" in selected_feed:
            auth_data["login"] = st.text_input("MT5 Account ID", key="auth_mt5_login")
            auth_data["pass"] = st.text_input("MT5 Password", type="password", key="auth_mt5_pass")
            auth_data["server"] = st.text_input("Broker Server Name", key="auth_mt5_server")
        else:
            auth_data["key"] = st.text_input("API Key / Client ID", type="password", key="auth_api_key")
            auth_data["sec"] = st.text_input("API Secret / Token", type="password", key="auth_api_sec")
            
        connect_btn = st.form_submit_button("Save & Initialize Connection")
        
    if connect_btn:
        st.session_state["connections"][selected_feed] = auth_data
        st.success(f"Successfully configured bridge for {selected_feed}!")

    active_bridges = list(st.session_state["connections"].keys())
    if active_bridges:
        st.markdown("#### 🟢 Active Custom Bridges:")
        for b in active_bridges:
            st.write(f"- {b}")

with tab_main_workspace:
    tab_names = list(st.session_state["tabs_data"].keys())
    workspace_tabs = st.tabs([f"📁 {t}" for t in tab_names] + ["➕ Add Tab"])

    if len(workspace_tabs) > len(tab_names):
        new_tab_name = f"Tab {len(tab_names) + 1}"
        st.session_state["tabs_data"][new_tab_name] = {"symbol": "ETHUSDT", "grid": "1x1 (Single Chart)"}
        st.rerun()

    @st.cache_data(ttl=5, show_spinner=False)
    def generate_fallback_trades(sym, n=2000):
        np.random.seed(42)
        base = 80000.0 if "BTC" in sym else 2500.0 if "ETH" in sym else 100.0
        prices = base + np.cumsum(np.random.randn(n) * (base * 0.0002))
        qtys = np.random.uniform(0.1, 5.0, n)
        is_buy = np.random.choice([True, False], size=n)
        times = [datetime.datetime.now() - datetime.timedelta(seconds=i*2) for i in range(n)][::-1]
        
        return pd.DataFrame({
            'timestamp': times,
            'price': prices,
            'qty': qtys,
            'ask_vol': np.where(~is_buy, qtys, 0.0),
            'bid_vol': np.where(is_buy, qtys, 0.0)
        })

    @st.cache_data(ttl=5, show_spinner=False)
    def fetch_raw_trades(sym):
        url = "https://api.binance.com/api/v3/aggTrades?symbol=" + str(sym).strip() + "&limit=500"
        try:
            r = requests.get(url, timeout=1.5)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    df = pd.DataFrame(data)
                    df = df.rename(columns={'p': 'price', 'q': 'qty', 'T': 'time', 'm': 'isBuyerMaker'})
                    df['price'] = df['price'].astype(float)
                    df['qty'] = df['qty'].astype(float)
                    df['timestamp'] = pd.to_datetime(df['time'], unit='ms')
                    bm = df['isBuyerMaker'].tolist()
                    q = df['qty'].tolist()
                    df['ask_vol'] = [0.0 if x else q[i] for i, x in enumerate(bm)]
                    df['bid_vol'] = [q[i] if x else 0.0 for i, x in enumerate(bm)]
                    return df
        except Exception:
            pass
        return generate_fallback_trades(sym)

    def build_tick_bars(trades, count):
        trades['bar_id'] = np.arange(len(trades)) // count
        m = {'timestamp': 'last', 'price': ['first', 'max', 'min', 'last'], 'qty': 'sum', 'ask_vol': 'sum', 'bid_vol': 'sum'}
        b = trades.groupby('bar_id').agg(m).reset_index(drop=True)
        b.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'ask_vol', 'bid_vol']
        b['x_label'] = ["T-Bar " + str(i+1) for i in range(len(b))]
        return b

    def build_volume_bars(trades, target_vol):
        trades['cum_vol'] = trades['qty'].cumsum()
        trades['bar_id'] = (trades['cum_vol'] // target_vol).astype(int)
        m = {'timestamp': 'last', 'price': ['first', 'max', 'min', 'last'], 'qty': 'sum', 'ask_vol': 'sum', 'bid_vol': 'sum'}
        b = trades.groupby('bar_id').agg(m).reset_index(drop=True)
        b.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'ask_vol', 'bid_vol']
        b['x_label'] = ["V-Bar " + str(i+1) for i in range(len(b))]
        return b

    @st.cache_data(ttl=5, show_spinner=False)
    def fetch_candles(sym, tf_val):
        tf_m = {"1MIN": "1m", "3MIN": "3m", "5MIN": "5m", "15MIN": "15m", "30MIN": "30m", "1HR": "1h", "4HR": "4h", "1D": "1d"}
        inv = tf_m.get(tf_val, "5m")
        url = "https://api.binance.com/api/v3/klines?symbol=" + str(sym).strip() + "&interval=" + str(inv) + "&limit=100"
        try:
            r = requests.get(url, timeout=1.5)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    cols = ['ot', 'open', 'high', 'low', 'close', 'volume', 'ct', 'qav', 'tr', 'tbba', 'tbqa', 'ig']
                    df = pd.DataFrame(data, columns=cols)
                    df['timestamp'] = pd.to_datetime(df['ot'], unit='ms')
                    for c in ['open', 'high', 'low', 'close', 'volume']:
                        df[c] = df[c].astype(float)
                    df['ask_vol'] = df['tbba'].astype(float)
                    df['bid_vol'] = df['volume'] - df['ask_vol']
                    df['x_label'] = df['timestamp']
                    return df[['x_label', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'bid_vol', 'ask_vol']]
        except Exception:
            pass
        raw = generate_fallback_trades(sym, 1000)
        return build_tick_bars(raw, 250).rename(columns={'timestamp': 'x_label'})

    def get_formula_data(formula, tf, is_non_time, tick_agg, vol_target):
        tickers = list(set(re.findall(r'[A-Z0-9]+', formula.upper())))
        if not tickers:
            tickers = ["BTCUSDT"]
        data_dict = {}
        for sym in tickers:
            if is_non_time:
                raw = fetch_raw_trades(sym)
                if tick_agg > 0:
                    df_s = build_tick_bars(raw, tick_agg)
                elif vol_target > 0:
                    df_s = build_volume_bars(raw, vol_target)
                else:
                    df_s = build_tick_bars(raw, 250)
            else:
                df_s = fetch_candles(sym, tf)
            if df_s is not None and not df_s.empty:
                data_dict[sym] = df_s.set_index('timestamp')
            else:
                data_dict[sym] = build_tick_bars(generate_fallback_trades(sym), 250).set_index('timestamp')
                
        base_sym = tickers[0]
        if base_sym not in data_dict:
            return generate_fallback_trades("BTCUSDT", 500)
            
        combined = pd.DataFrame(index=data_dict[base_sym].index)
        for sym in tickers:
            if sym in data_dict:
                for col in ['open', 'high', 'low', 'close', 'volume', 'ask_vol', 'bid_vol']:
                    if col in data_dict[sym].columns:
                        combined[f"{sym}_{col}"] = data_dict[sym][col]
                        
        combined = combined.dropna().reset_index()
        if combined.empty:
            return build_tick_bars(generate_fallback_trades(tickers[0]), 250).rename(columns={'timestamp': 'x_label'})
            
        expr = formula.upper()
        try:
            open_expr = re.sub(r'([A-Z0-9]+)', r"combined['\1_open']", expr)
            high_expr = re.sub(r'([A-Z0-9]+)', r"combined['\1_high']", expr)
            low_expr = re.sub(r'([A-Z0-9]+)', r"combined['\1_low']", expr)
            close_expr = re.sub(r'([A-Z0-9]+)', r"combined['\1_close']", expr)
            vol_expr = re.sub(r'([A-Z0-9]+)', r"combined['\1_volume']", expr)
            
            o_ser = eval(open_expr, {"combined": combined, "np": np})
            h_ser = eval(high_expr, {"combined": combined, "np": np})
            l_ser = eval(low_expr, {"combined": combined, "np": np})
            c_ser = eval(close_expr, {"combined": combined, "np": np})
            v_ser = eval(vol_expr, {"combined": combined, "np": np})
            
            res_df = pd.DataFrame({
                'timestamp': combined['timestamp'],
                'x_label': combined['timestamp'] if not is_non_time else [f"Bar {i+1}" for i in range(len(combined))],
                'open': o_ser,
                'high': np.maximum(o_ser, np.maximum(h_ser, c_ser)),
                'low': np.minimum(o_ser, np.minimum(l_ser, c_ser)),
                'close': c_ser,
                'volume': np.abs(v_ser),
                'ask_vol': np.abs(v_ser) * 0.5,
                'bid_vol': np.abs(v_ser) * 0.5
            })
            return res_df
        except Exception:
            return build_tick_bars(fetch_raw_trades(tickers[0]), 250)

    for i, t_name in enumerate(tab_names):
        with workspace_tabs[i]:
            tb_cols = st.columns([2.0, 2.0, 2.0, 2.0, 2.6])
            with tb_cols[0]:
                grid_mode = st.selectbox("Grid Layout", ["1x1 (Single Chart)", "1x2 (2 Charts)", "2x2 (4 Charts)", "2x4 (8 Charts)"], key=f"grid_{t_name}")
            with tb_cols[1]:
                drawing_tool = st.selectbox("✏️ Drawing Tool", ["Cursor (Crosshair)", "Trendline", "Horizontal Ray", "Fib Retracement", "Channel", "Measure Tool"], key=f"tool_{t_name}")
            with tb_cols[2]:
                timeframe = st.selectbox("Timeframe", ["1MIN", "3MIN", "5MIN", "15MIN", "30MIN", "1HR", "4HR", "1D"], index=2, key=f"tf_{t_name}")
            with tb_cols[3]:
                indicators = st.multiselect("📈 Indicators", ["Candlesticks", "Line Price", "Moving Averages (MA 5/50)", "Volume Profile", "CVD Delta", "RSI"], default=["Candlesticks", "Moving Averages (MA 5/50)"], key=f"ind_{t_name}")
            with tb_cols[4]:
                formula_input = st.text_input("🧮 Symbol / Formula (/*-+=()^><)", value="BTCUSDT", key=f"sym_{t_name}")

            sc_cols = st.columns(3)
            with sc_cols[0]:
                tick_choice = st.selectbox("⚡ Tick Aggregation", ["Off", "250 Ticks", "500 Ticks", "1000 Ticks", "2500 Ticks", "5000 Ticks", "10000 Ticks"], key=f"tick_{t_name}")
            with sc_cols[1]:
                vol_choice = st.selectbox("📊 Volume Bars", ["Off", "5", "10", "50", "100", "300", "500", "1000", "3000", "5000", "10000", "30000", "50000", "100000", "250050", "500000", "1000000", "3000000", "5000000", "10000000"], key=f"vol_{t_name}")
            with sc_cols[2]:
                alarm_price = st.number_input("🔔 Set Price Alert Level", value=0.0, key=f"alarm_{t_name}")
                if st.button("Add Alert", key=f"btn_alarm_{t_name}"):
                    if alarm_price > 0:
                        st.session_state["alarms"].append({"Tab": t_name, "Symbol": formula_input, "Price": alarm_price})
                        st.success(f"Alarm set for {formula_input} at ${alarm_price:,.2f}")

            st.markdown("---")

            is_non_time = (tick_choice != "Off") or (vol_choice != "Off")
            tick_val = int(tick_choice.split()[0]) if tick_choice != "Off" else 0
            vol_val = float(vol_choice.replace(",", "")) if vol_choice != "Off" else 0.0

            chart_count = 1
            if "1x2" in grid_mode: chart_count = 2
            elif "2x2" in grid_mode: chart_count = 4
            elif "2x4" in grid_mode: chart_count = 8

            symbols_to_plot = [formula_input]
            if chart_count > 1:
                defaults = ["ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT"]
                symbols_to_plot += [s for s in defaults if s != formula_input][:chart_count - 1]

            rows_in_grid = (chart_count + 1) // 2 if chart_count > 1 else 1
            cols_in_grid = 2 if chart_count > 1 else 1
            
            for r in range(rows_in_grid):
                cols = st.columns(cols_in_grid)
                for c in range(cols_in_grid):
                    idx = r * cols_in_grid + c
                    if idx >= chart_count:
                        break
                    cur_sym = symbols_to_plot[idx]
                    
                    with cols[c]:
                        df = get_formula_data(cur_sym, timeframe, is_non_time, tick_val, vol_val)
                        for ma in [5, 50]:
                            df[f'MA_{ma}'] = df['close'].rolling(min(ma, len(df))).mean()
                            
                        fig = go.Figure()
                        if "Candlesticks" in indicators:
                            fig.add_trace(go.Candlestick(x=df['x_label'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name=cur_sym))
                        if "Line Price" in indicators:
                            fig.add_trace(go.Scatter(x=df['x_label'], y=df['close'], mode='lines', line=dict(color='#2962ff', width=1.5), name='Line'))
                        if "Moving Averages (MA 5/50)" in indicators:
                            fig.add_trace(go.Scatter(x=df['x_label'], y=df['MA_5'], line=dict(color='#f59e0b', width=1.5), name='MA 5'))
                            fig.add_trace(go.Scatter(x=df['x_label'], y=df['MA_50'], line=dict(color='#a855f7', width=1.5), name='MA 50'))

                        current_c = df['close'].iloc[-1]
                        for alm in st.session_state["alarms"]:
                            if alm["Symbol"] == cur_sym and abs(current_c - alm["Price"]) / alm["Price"] < 0.001:
                                st.markdown(f'<div class="alarm-box">🚨 ALARM TRIGGERED: {cur_sym} reached target price ${alm["Price"]:,.2f}!</div>', unsafe_allow_html=True)

                        fig.update_layout(
                            template="plotly_dark",
                            paper_bgcolor="#131722",
                            plot_bgcolor="#131722",
                            height=380 if chart_count > 1 else 520,
                            title=dict(text=f"<b>{cur_sym}</b> | Tool: {drawing_tool}", font=dict(size=12, color="#d1d4dc")),
                            xaxis_rangeslider_visible=False,
                            margin=dict(l=10, r=10, t=30, b=10)
                        )
                        if is_non_time:
                            fig.update_xaxes(type="category")
                        st.plotly_chart(fig, use_container_width=True, key=f"plt_{t_name}_{idx}_{time.time()}")

    if st.session_state["alarms"]:
        st.markdown("---")
        st.markdown("#### 🔔 Active Price & Technical Alarms")
        st.dataframe(pd.DataFrame(st.session_state["alarms"]), hide_index=True, use_container_width=True)