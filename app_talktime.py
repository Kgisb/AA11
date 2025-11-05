
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from io import BytesIO

# -------------------------------
# Utility Parsers & Helpers
# -------------------------------

def _coalesce_column(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    # case-insensitive fallback
    lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None

def _parse_duration_to_seconds(x):
    """
    Accepts integer/float seconds, or strings like 'MM:SS'/'HH:MM:SS'.
    Returns seconds (float). Invalid -> np.nan.
    """
    if pd.isna(x):
        return np.nan
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    s = str(x).strip()
    # Try plain number
    try:
        return float(s)
    except:
        pass
    # Try HH:MM:SS or MM:SS
    parts = s.split(':')
    try:
        parts = [float(p) for p in parts]
    except:
        return np.nan
    if len(parts) == 2:
        mm, ss = parts
        return mm * 60 + ss
    if len(parts) == 3:
        hh, mm, ss = parts
        return hh * 3600 + mm * 60 + ss
    return np.nan

def _parse_datetime(x):
    if pd.isna(x):
        return pd.NaT
    # Try pandas to_datetime with dayfirst and infer
    try:
        return pd.to_datetime(x, errors="coerce", utc=True, infer_datetime_format=True, dayfirst=False)
    except:
        return pd.NaT

def _download_df_button(df, filename):
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("Download CSV", csv, file_name=filename, mime="text/csv")

# -------------------------------
# App
# -------------------------------
st.set_page_config(page_title="TalkTime App", layout="wide")
st.title("📞 TalkTime App")

with st.sidebar:
    st.header("Upload & Settings")
    uploaded = st.file_uploader("Upload activity feed CSV", type=["csv"])

    st.markdown("**Mode**")
    mode = st.radio(
        "Counting rule",
        options=["Talktime (>= threshold sec)", "Overall (all calls)"],
        index=0
    )
    threshold = st.slider("Talktime threshold (seconds)", 10, 300, 60, 5,
                          help="Calls with duration >= this are counted in 'Talktime' mode.")

    st.markdown("---")
    st.caption("Tip: If columns don't align, use the Mapping section below to map your file's columns.")

    st.markdown("---")
    st.subheader("Column Mapping (optional)")
    map_agent = st.text_input("Agent/User column name (e.g., Owner, Agent, User, Student/Academic Counsellor)", value="")
    map_country = st.text_input("Country column name (e.g., Country, Country/Region)", value="")
    map_duration = st.text_input("Duration column name (e.g., Call Duration, Duration, Talk Time)", value="")
    map_start = st.text_input("Call start time column (e.g., Start Time, Call Start Time, Created At, Timestamp)", value="")

    st.markdown("---")
    st.caption("Filter controls will appear after a file is uploaded.")

if uploaded is None:
    st.info("Please upload your CSV to begin.")
    st.stop()

# Read data
try:
    df_raw = pd.read_csv(uploaded, low_memory=False)
except Exception as e:
    st.error(f"Could not read CSV: {e}")
    st.stop()

df = df_raw.copy()

# Attempt to find columns if user didn't map
agent_col = map_agent or _coalesce_column(df, ["Owner", "Agent", "User", "Student/Academic Counsellor", "Student/Academic Counselor", "Assigned To", "Rep", "Agent Name"])
country_col = map_country or _coalesce_column(df, ["Country", "Country/Region", "Country Name"])
duration_col = map_duration or _coalesce_column(df, ["Call Duration", "Duration", "Talk Time", "CallDuration", "Call_Duration"])
start_col = map_start or _coalesce_column(df, ["Start Time", "Call Start Time", "Created At", "Timestamp", "Call Start", "Started At", "Date/Time", "Datetime"])

missing = []
if agent_col is None: missing.append("Agent/User")
if country_col is None: missing.append("Country")
if duration_col is None: missing.append("Duration")
if start_col is None: missing.append("Start Time/Timestamp")

if missing:
    st.warning("Missing column(s): " + ", ".join(missing) + ". You can provide mappings in the sidebar.")
    # we can still proceed with what's available, but some views may not render.

# Parse duration
if duration_col is not None:
    df["_duration_sec"] = df[duration_col].apply(_parse_duration_to_seconds)
else:
    df["_duration_sec"] = np.nan

# Parse timestamp & build helpers
if start_col is not None:
    dt = df[start_col].apply(_parse_datetime)
    # Normalize to local naive time for grouping by hour; user timezone is Asia/Kolkata (+05:30)
    # We'll convert UTC to Asia/Kolkata if tz-aware else treat as naive and localize.
    try:
        dt = pd.to_datetime(dt, utc=True)
        dt_local = dt.dt.tz_convert("Asia/Kolkata")
    except:
        # If conversion fails (naive), just localize to Asia/Kolkata
        dt_local = pd.to_datetime(dt).dt.tz_localize("Asia/Kolkata", nonexistent='NaT', ambiguous='NaT')
    df["_dt_local"] = dt_local
    df["_date"] = df["_dt_local"].dt.date
    df["_hour"] = df["_dt_local"].dt.hour
else:
    df["_dt_local"] = pd.NaT
    df["_date"] = pd.NaT
    df["_hour"] = np.nan

# Sidebar filters after parsing
with st.sidebar:
    if start_col is not None:
        min_date = pd.to_datetime(df["_dt_local"]).min()
        max_date = pd.to_datetime(df["_dt_local"]).max()
        if pd.isna(min_date) or pd.isna(max_date):
            st.caption("No valid dates detected.")
            date_range = None
        else:
            st.subheader("Date Range")
            dr = st.date_input("Select date range (local time)", value=(min_date.date(), max_date.date()))
            if isinstance(dr, tuple) and len(dr) == 2:
                start_date, end_date = dr
                date_range = (pd.Timestamp(start_date, tz="Asia/Kolkata"), pd.Timestamp(end_date, tz="Asia/Kolkata") + pd.Timedelta(days=1))
            else:
                date_range = None
    else:
        date_range = None

    # Agent filter
    if agent_col is not None:
        agents = sorted([str(x) for x in df[agent_col].dropna().unique().tolist()])
        sel_agents = st.multiselect("Filter: Agents", agents, default=agents[: min(10, len(agents))])
    else:
        sel_agents = None

    # Country filter
    if country_col is not None:
        countries = sorted([str(x) for x in df[country_col].dropna().unique().tolist()])
        sel_countries = st.multiselect("Filter: Countries", countries, default=countries[: min(10, len(countries))])
    else:
        sel_countries = None

# Apply filters
df_f = df.copy()
if date_range and start_col is not None:
    s, e = date_range
    df_f = df_f[(df_f["_dt_local"] >= s) & (df_f["_dt_local"] < e)]
if sel_agents is not None:
    df_f = df_f[df_f[agent_col].astype(str).isin(sel_agents)]
if sel_countries is not None:
    df_f = df_f[df_f[country_col].astype(str).isin(sel_countries)]

# Apply counting rule
if mode.startswith("Talktime"):
    # Only keep rows with duration >= threshold
    if duration_col is not None:
        df_rules = df_f[df_f["_duration_sec"] >= float(threshold)].copy()
    else:
        df_rules = df_f.copy()  # can't filter without duration
else:
    df_rules = df_f.copy()

# KPI Cards
col1, col2, col3, col4 = st.columns(4)
total_calls = len(df_rules)
avg_dur = df_rules["_duration_sec"].mean() if "_duration_sec" in df_rules.columns else np.nan
median_dur = df_rules["_duration_sec"].median() if "_duration_sec" in df_rules.columns else np.nan
unique_agents = df_rules[agent_col].nunique() if agent_col is not None else 0

col1.metric("Total Calls", f"{total_calls:,}")
col2.metric("Avg Duration (sec)", f"{avg_dur:,.1f}" if not np.isnan(avg_dur) else "NA")
col3.metric("Median Duration (sec)", f"{median_dur:,.1f}" if not np.isnan(median_dur) else "NA")
col4.metric("Agents", f"{unique_agents}")

st.markdown("### 1) Agent-wise Talktime Detail")
if agent_col is not None:
    agg_funcs = {"_duration_sec": ["count", "sum", "mean", "median"]}
    g_agent = (df_rules
               .groupby(agent_col, dropna=False)
               .agg(agg_funcs))
    g_agent.columns = ["Call Count", "Total Duration (sec)", "Avg Duration (sec)", "Median Duration (sec)"]
    g_agent = g_agent.reset_index().sort_values("Total Duration (sec)", ascending=False)
    st.dataframe(g_agent, use_container_width=True)
    _download_df_button(g_agent, "agent_wise_talktime.csv")
else:
    st.info("Agent/User column not found or mapped.")

st.markdown("### 2) Country-wise Talktime Detail")
if country_col is not None:
    agg_funcs = {"_duration_sec": ["count", "sum", "mean", "median"]}
    g_country = (df_rules
               .groupby(country_col, dropna=False)
               .agg(agg_funcs))
    g_country.columns = ["Call Count", "Total Duration (sec)", "Avg Duration (sec)", "Median Duration (sec)"]
    g_country = g_country.reset_index().sort_values("Total Duration (sec)", ascending=False)
    st.dataframe(g_country, use_container_width=True)
    _download_df_button(g_country, "country_wise_talktime.csv")
else:
    st.info("Country column not found or mapped.")

st.markdown("### 3) Agent x Country Talktime Matrix")
if agent_col is not None and country_col is not None:
    pivot = (df_rules
             .groupby([agent_col, country_col], dropna=False)["_duration_sec"]
             .sum()
             .reset_index(name="Total Duration (sec)"))
    st.dataframe(pivot.sort_values("Total Duration (sec)", ascending=False), use_container_width=True)
    _download_df_button(pivot, "agent_country_talktime.csv")
else:
    st.info("Need both Agent and Country columns.")

st.markdown("### 4) 24-hour Attempts Bubble Graph (by local hour)")
if start_col is not None:
    # attempts = number of rows per hour (independent of duration rule)
    attempts = (df_f  # use filtered set but before duration rule for "attempts"
                .assign(hour=lambda d: d["_hour"])
                .dropna(subset=["_hour"])
                .groupby("hour")
                .size()
                .reset_index(name="Attempts"))
    if attempts.empty:
        st.info("No timestamp data available to plot attempts by hour.")
    else:
        # Bubble chart using Altair
        attempts["hour"] = attempts["hour"].astype(int)
        chart = alt.Chart(attempts).mark_circle().encode(
            x=alt.X("hour:O", title="Hour of Day (0–23)"),
            y=alt.Y("Attempts:Q", title="Call Attempts"),
            size=alt.Size("Attempts:Q", legend=None),
            tooltip=["hour:O", "Attempts:Q"]
        ).properties(height=300).interactive()
        st.altair_chart(chart, use_container_width=True)
        _download_df_button(attempts, "attempts_by_hour.csv")
else:
    st.info("No timestamp/start time column found or mapped.")

st.markdown("---")
st.caption("Note: 'Talktime' mode counts only calls with duration >= threshold seconds. 'Overall' counts all calls.")
