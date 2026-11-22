import json
import math
from datetime import datetime
import pandas as pd
import requests
import streamlit as st
from PIL import Image
from google import genai
from google.genai import types

# ---------------------------------------------------------
# 1. PAGE CONFIG & SESSION STATE
# ---------------------------------------------------------
st.set_page_config(
    page_title="Stage 2 Trade Planner & Tracker",
    page_icon="📈",
    layout="wide"
)

if "trades" not in st.session_state:
    st.session_state.trades = pd.DataFrame(columns=[
        "Date", "Ticker", "EntryType", "Entry", "Qty",
        "SquatTrim_SL", "Hard_SL", "Capital", "Risk_INR",
        "ProfitLock_20pct", "Trail_EMA", "Status"
    ])

if "extracted" not in st.session_state:
    st.session_state.extracted = None


# ---------------------------------------------------------
# 2. HELPER FUNCTIONS (AI VISION & TELEGRAM)
# ---------------------------------------------------------
def get_secret(key_name, fallback=""):
    try:
        return st.secrets[key_name]
    except Exception:
        return fallback


def send_telegram(token, chat_id, message):
    if not token or not chat_id:
        return False, "Missing Telegram Bot Token or Chat ID."
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True, "Sent to Telegram!"
        return False, f"Telegram Error: {resp.text}"
    except Exception as e:
        return False, f"Connection Error: {e}"


def analyze_chart_with_gemini(api_key, image: Image.Image):
    client = genai.Client(api_key=api_key)
    prompt = """
    You are an expert Indian equity technical analyst reading a TradingView Weekly (1W) or Daily (1D) chart screenshot.
    Extract the exact visible numbers and return ONLY a valid JSON object with these keys:
    {
      "ticker": "string (NSE/BSE symbol, e.g., BELRISE)",
      "cmp": float (current closing price),
      "candle_low": float (low of the latest/breakout candle),
      "ema10": float (yellow 10W EMA or fast EMA value),
      "ema20": float (cyan/blue 20W/21D EMA value),
      "ema40": float (red 40W/50D EMA value),
      "mcap_cr": float (Market Cap in Crores, e.g., 22857.0),
      "avg_vol_cr": float (Avg Rupee Volume in Crores; convert Lakhs to Crores, e.g., 16.39L -> 0.16),
      "beta": float (Beta value if shown, else 1.0),
      "rs_value": float (Relative Strength value in bottom pane, negative if below 0, else 0.0),
      "rs_status": "string ('Outperformance' or 'Underperformance')",
      "stage": "string (e.g., 'S1 -> S2', 'S2', 'S3 -> S2', 'S4')",
      "resistance": float (nearest visible overhead resistance / swing high price),
      "notes": "string (2 concise bullet points on volume, base structure, and upper wicks)"
    }
    If any numeric field is not visible, estimate carefully from the chart axis or use 0.0.
    """
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[prompt, image],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1
        )
    )
    return json.loads(response.text)


# ---------------------------------------------------------
# 3. SIDEBAR: PORTFOLIO & GUARDRAILS
# ---------------------------------------------------------
st.sidebar.title("⚙️ Risk Guardrails")

total_capital = st.sidebar.number_input(
    "Total Trading Capital (₹)", min_value=50000, value=1000000, step=50000
)
risk_pct = st.sidebar.select_slider(
    "Max Risk per Trade (%)",
    options=[0.25, 0.50, 0.75, 1.00, 1.50, 2.00],
    value=1.00,
    help="Himanshu recommends 0.25%–0.50% in choppy markets and 1.0% in strong trends."
)
max_alloc_pct = st.sidebar.slider(
    "Max Capital per Stock (%)", min_value=15, max_value=50, value=35, step=5
)

st.sidebar.markdown("---")
st.sidebar.subheader("🛡️ Auto-Filter Rules")
min_mcap = st.sidebar.number_input("Min Market Cap (₹ Cr)", value=3000.0, step=500.0)
min_vol_cr = st.sidebar.number_input("Min Avg ₹ Volume (Cr)", value=1.0, step=0.5)
max_ext_pct = st.sidebar.number_input("Max Extension above 10W EMA (%)", value=10.0, step=1.0)

st.sidebar.markdown("---")
st.sidebar.subheader("🔑 API Keys (Auto-loads from Secrets)")
gemini_key = st.sidebar.text_input(
    "Gemini API Key", value=get_secret("GEMINI_API_KEY"), type="password"
)
tg_token = st.sidebar.text_input(
    "Telegram Bot Token", value=get_secret("TELEGRAM_BOT_TOKEN"), type="password"
)
tg_chat_id = st.sidebar.text_input(
    "Telegram Chat ID", value=get_secret("TELEGRAM_CHAT_ID")
)


# ---------------------------------------------------------
# 4. MAIN TABS
# ---------------------------------------------------------
st.title("📈 Stage 2 Chart-to-Trade-Plan (Himanshu SL Mode)")
tab1, tab2, tab3 = st.tabs([
    "1️⃣ Chart → Trade Plan",
    "2️⃣ Active Positions Tracker",
    "3️⃣ Setup & Telegram"
])

# ==================== TAB 1: CHART TO TRADE PLAN ====================
with tab1:
    uploaded_file = st.file_uploader(
        "Upload TradingView Weekly (1W) or Daily (1D) Chart Screenshot",
        type=["png", "jpg", "jpeg"]
    )

    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, use_container_width=True)

        if st.button("🔍 Read Chart with Gemini AI", type="primary"):
            if not gemini_key:
                st.error("Please enter your Gemini API Key in the sidebar or Streamlit Secrets.")
            else:
                with st.spinner("Reading chart overlays & structure..."):
                    try:
                        st.session_state.extracted = analyze_chart_with_gemini(gemini_key, img)
                        st.success("Chart data extracted! Verify the numbers below.")
                    except Exception as e:
                        st.error(f"Could not read chart: {e}")

    data = st.session_state.extracted or {
        "ticker": "", "cmp": 0.0, "candle_low": 0.0, "ema10": 0.0, "ema20": 0.0,
        "ema40": 0.0, "mcap_cr": 0.0, "avg_vol_cr": 0.0, "beta": 1.0,
        "rs_value": 0.0, "rs_status": "Outperformance", "stage": "S1 -> S2",
        "resistance": 0.0, "notes": ""
    }

    with st.expander("✏️ Verify Chart Numbers & Select Entry Style", expanded=True):
        entry_style = st.selectbox(
            "Himanshu Entry & Stop-Loss Style",
            [
                "Pivot / Standard Breakout (Base Low Hard SL + 50% Squat Trim)",
                "Shakeout / EMA Reclaim (3.5% below Key EMA)",
                "Pullback Entry (Pullback Candle Low)",
                "Gap-Up Entry (Gap Window Low)"
            ]
        )

        c1, c2, c3, c4 = st.columns(4)
        ticker = c1.text_input("Ticker", value=str(data.get("ticker", ""))).upper()
        cmp_price = c2.number_input("Current Price (₹)", value=float(data.get("cmp", 0.0)), step=1.0)
        candle_low = c3.number_input("Breakout / Candle Low (₹)", value=float(data.get("candle_low", 0.0)), step=1.0)
        resistance = c4.number_input("Overhead Resistance (₹)", value=float(data.get("resistance", 0.0)), step=1.0)

        c5, c6, c7, c8 = st.columns(4)
        ema10 = c5.number_input("10W EMA (₹)", value=float(data.get("ema10", 0.0)), step=1.0)
        ema20 = c6.number_input("20W / 21D EMA (₹)", value=float(data.get("ema20", 0.0)), step=1.0)
        ema40 = c7.number_input("40W / 50D EMA (₹)", value=float(data.get("ema40", 0.0)), step=1.0)
        mcap_cr = c8.number_input("Market Cap (₹ Cr)", value=float(data.get("mcap_cr", 0.0)), step=100.0)

        c9, c10, c11 = st.columns(3)
        avg_vol_cr = c9.number_input("Avg ₹ Volume (Cr)", value=float(data.get("avg_vol_cr", 0.0)), step=0.5)
        rs_val = c10.number_input("RS Value", value=float(data.get("rs_value", 0.0)), step=0.5)
        rs_status = c11.selectbox(
            "RS Status",
            ["Outperformance", "Underperformance"],
            index=0 if "out" in str(data.get("rs_status", "")).lower() else 1
        )

        # Auto-calculate suggested Hard SL based on selected Himanshu Entry Style
        if "Shakeout" in entry_style and ema40 > 0:
            suggested_sl = round(ema40 * 0.965, 2)  # 3.5% below key EMA
        elif ("Pullback" in entry_style or "Gap-Up" in entry_style) and candle_low > 0:
            suggested_sl = round(candle_low * 0.995, 2)
        elif ema40 > 0:
            suggested_sl = round(ema40 * 0.99, 2)   # Base / 40W EMA low
        else:
            suggested_sl = round(cmp_price * 0.90, 2)

        suggested_squat = round(candle_low, 2) if candle_low > suggested_sl else round(ema10, 2)

        s_col1, s_col2 = st.columns(2)
        hard_sl = s_col1.number_input("Hard System Stop-Loss (₹)", value=float(suggested_sl), step=1.0)
        squat_sl = s_col2.number_input(
            "50% Squat-Trim Trigger (₹)",
            value=float(suggested_squat if suggested_squat < cmp_price else hard_sl),
            step=1.0,
            help="If price falls back into range and breaks this level, trim 50% immediately."
        )

        if data.get("notes"):
            st.info(f"**AI Chart Notes:** {data['notes']}")

    # ---------------- HARD-CODED RULES & MATH ENGINE ----------------
    if cmp_price > 0 and hard_sl > 0 and cmp_price > hard_sl:
        ext_10w = ((cmp_price - ema10) / ema10 * 100) if ema10 > 0 else 0.0
        risk_per_share = cmp_price - hard_sl
        sl_pct = (risk_per_share / cmp_price) * 100

        # Himanshu Position Sizing Formula: (100 / SL%) * risk_pct
        formula_alloc_pct = (100.0 / sl_pct) * risk_pct
        final_alloc_pct = min(formula_alloc_pct, float(max_alloc_pct))
        max_risk_inr = total_capital * (risk_pct / 100.0)

        total_qty = math.floor((total_capital * (final_alloc_pct / 100.0)) / cmp_price)
        if total_qty * risk_per_share > max_risk_inr:
            total_qty = math.floor(max_risk_inr / risk_per_share)

        deployed_cap = total_qty * cmp_price
        actual_risk_inr = total_qty * risk_per_share

        # Squat Trim Math (50% cut at squat_sl, 50% at hard_sl)
        half_qty = total_qty // 2
        rem_qty = total_qty - half_qty
        if squat_sl > hard_sl and squat_sl < cmp_price:
            hybrid_risk_inr = (half_qty * (cmp_price - squat_sl)) + (rem_qty * risk_per_share)
        else:
            hybrid_risk_inr = actual_risk_inr

        # Profit Booking Targets (+20% to +25%)
        profit_20 = round(cmp_price * 1.20, 2)
        profit_25 = round(cmp_price * 1.25, 2)

        # Auto-Verdict Filter
        fails, warnings = [], []
        if mcap_cr < min_mcap:
            fails.append(f"Market Cap (₹{mcap_cr:,.0f} Cr) is below ₹{min_mcap:,.0f} Cr minimum.")
        if avg_vol_cr < min_vol_cr:
            fails.append(f"Avg Turnover (₹{avg_vol_cr:.2f} Cr) is below ₹{min_vol_cr:.2f} Cr minimum.")
        if rs_status == "Underperformance" or rs_val < 0:
            fails.append(f"Relative Strength is negative/underperforming ({rs_val}).")
        if ext_10w > max_ext_pct:
            warnings.append(f"Extended +{ext_10w:.1f}% above 10W EMA (Limit: {max_ext_pct:.1f}%). Wait for pullback.")

        if fails:
            verdict = "🔴 AVOID / PASS"
            st.error(f"### Verdict: {verdict}")
            for f in fails:
                st.write(f"❌ {f}")
        elif warnings:
            verdict = "🟡 WAIT FOR PULLBACK"
            st.warning(f"### Verdict: {verdict}")
            for w in warnings:
                st.write(f"⚠️ {w}")
        else:
            verdict = "🟢 ACTIONABLE SETUP"
            st.success(f"### Verdict: {verdict}")
            st.write(f"✅ Passes Market Cap, Liquidity, RS, and Extension (+{ext_10w:.1f}% vs 10W EMA) rules.")

        st.markdown("### 📋 Clean Trade Plan (Himanshu Risk Framework)")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Position Size", f"{total_qty} shares", f"₹{deployed_cap:,.0f} ({final_alloc_pct:.1f}% cap)")
        m2.metric("Hard System SL", f"₹{hard_sl:.2f}", f"-{sl_pct:.1f}% (Max: ₹{actual_risk_inr:,.0f})")
        m3.metric("50% Squat Trim", f"₹{squat_sl:.2f}", f"Hybrid Risk: ₹{hybrid_risk_inr:,.0f}")
        m4.metric("Book 30–50% Profit", f"₹{profit_20:.1f}–₹{profit_25:.1f}", f"Trail rest on 21/20W EMA")

        plan_df = pd.DataFrame([
            {
                "Step": "1. Entry",
                "Price / Trigger": f"₹{cmp_price:.2f} ({entry_style.split(' (')[0]})",
                "Action": f"Buy {total_qty} shares (₹{deployed_cap:,.0f})"
            },
            {
                "Step": "2. Squat Trim (Choppy Market Shield)",
                "Price / Trigger": f"Breaks below ₹{squat_sl:.2f}",
                "Action": f"Trim 50% ({half_qty} shares) to cut total risk to ₹{hybrid_risk_inr:,.0f}"
            },
            {
                "Step": "3. Final Hard Stop-Loss",
                "Price / Trigger": f"System GTT at ₹{hard_sl:.2f}",
                "Action": f"Exit remaining shares completely (Never lose > {risk_pct}%)"
            },
            {
                "Step": "4. Profit Lock & Trail",
                "Price / Trigger": f"₹{profit_20:.2f} (+20%) to ₹{profit_25:.2f} (+25%)",
                "Action": f"Book 30%–50% profit; trail rest on 20W/21D EMA (₹{ema20:.2f}) & 40W EMA (₹{ema40:.2f})"
            }
        ])
        st.dataframe(plan_df, use_container_width=True, hide_index=True)

        # Action Buttons
        b1, b2 = st.columns(2)
        tg_msg = (
            f"*{verdict}: {ticker}*\n"
            f"Style: {entry_style.split(' (')[0]}\n"
            f"CMP: ₹{cmp_price:.2f} | 10W EMA: ₹{ema10:.2f} (+{ext_10w:.1f}%)\n"
            f"MCap: ₹{mcap_cr:,.0f} Cr | Vol: ₹{avg_vol_cr:.2f} Cr | RS: {rs_val}\n\n"
            f"*Qty:* {total_qty} shares (₹{deployed_cap:,.0f})\n"
            f"*50% Squat Trim:* ₹{squat_sl:.2f} (Hybrid Risk: ₹{hybrid_risk_inr:,.0f})\n"
            f"*Hard System SL:* ₹{hard_sl:.2f} (Max Risk: ₹{actual_risk_inr:,.0f})\n"
            f"*Book 30–50%:* ₹{profit_20:.1f}–₹{profit_25:.1f}\n"
            f"*Trail Exit:* 20W/21D EMA (₹{ema20:.1f}) / 40W EMA (₹{ema40:.1f})"
        )

        if b1.button("💾 Save to Active Trades", use_container_width=True):
            new_row = pd.DataFrame([{
                "Date": datetime.now().strftime("%Y-%m-%d"),
                "Ticker": ticker or "UNKNOWN",
                "EntryType": entry_style.split(" (")[0],
                "Entry": cmp_price,
                "Qty": total_qty,
                "SquatTrim_SL": squat_sl,
                "Hard_SL": hard_sl,
                "Capital": round(deployed_cap, 2),
                "Risk_INR": round(actual_risk_inr, 2),
                "ProfitLock_20pct": profit_20,
                "Trail_EMA": ema20,
                "Status": "Open"
            }])
            st.session_state.trades = pd.concat([st.session_state.trades, new_row], ignore_index=True)
            st.success(f"Saved {ticker} to Active Positions Tracker!")
            if tg_token and tg_chat_id:
                send_telegram(tg_token, tg_chat_id, f"✅ *SAVED TO TRACKER*\n\n{tg_msg}")

        if b2.button("📲 Send Plan to Telegram", use_container_width=True):
            ok, msg = send_telegram(tg_token, tg_chat_id, tg_msg)
            if ok:
                st.success(msg)
            else:
                st.error(msg)


# ==================== TAB 2: ACTIVE POSITIONS TRACKER ====================
with tab2:
    st.subheader("📂 Active Positions & CSV Backup")

    col_up, col_down = st.columns(2)
    csv_upload = col_up.file_uploader("Upload Saved Trades CSV", type=["csv"])
    if csv_upload is not None:
        st.session_state.trades = pd.read_csv(csv_upload)
        st.success("Loaded trades from CSV!")

    if not st.session_state.trades.empty:
        csv_bytes = st.session_state.trades.to_csv(index=False).encode("utf-8")
        col_down.download_button(
            "⬇️ Download Trades CSV Backup",
            data=csv_bytes,
            file_name=f"stage2_trades_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )

    open_df = st.session_state.trades[st.session_state.trades["Status"] == "Open"]
    deployed = open_df["Capital"].sum() if not open_df.empty else 0.0
    total_open_risk = open_df["Risk_INR"].sum() if not open_df.empty else 0.0

    s1, s2, s3 = st.columns(3)
    s1.metric("Open Positions", len(open_df))
    s2.metric("Capital Deployed", f"₹{deployed:,.0f}", f"{(deployed/total_capital)*100:.1f}% of capital")
    s3.metric("Total Open Risk", f"₹{total_open_risk:,.0f}", f"{(total_open_risk/total_capital)*100:.2f}% of capital")

    st.markdown("#### Edit Positions Directly (Update Trailing SL or Status)")
    edited_df = st.data_editor(
        st.session_state.trades,
        num_rows="dynamic",
        use_container_width=True
    )
    if st.button("🔄 Recalculate & Save Edits"):
        edited_df["Capital"] = edited_df["Entry"] * edited_df["Qty"]
        edited_df["Risk_INR"] = ((edited_df["Entry"] - edited_df["Hard_SL"]).clip(lower=0)) * edited_df["Qty"]
        st.session_state.trades = edited_df
        st.success("Tracker updated! Remember to download your CSV backup.")


# ==================== TAB 3: SETUP & TELEGRAM ====================
with tab3:
    st.subheader("🔐 Streamlit Cloud Secrets Setup")
    st.write("Paste this into **Streamlit Cloud → App Settings → Secrets** so your keys load automatically:")
    st.code(
        'GEMINI_API_KEY = "your_gemini_api_key_here"\n'
        'TELEGRAM_BOT_TOKEN = "your_bot_token_here"\n'
        'TELEGRAM_CHAT_ID = "your_chat_id_here"',
        language="toml"
    )
    if st.button("🧪 Send Test Message to Telegram"):
        ok, msg = send_telegram(tg_token, tg_chat_id, "🚀 *Stage 2 Trade Planner (Himanshu SL Mode)* is live!")
        if ok:
            st.success(msg)
        else:
            st.error(msg)
