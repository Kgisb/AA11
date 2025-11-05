
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from difflib import SequenceMatcher

APP_TITLE = "📞 TalkTime App — v3.6 (B2C radio + MT Team checkbox)"
TZ = "Asia/Kolkata"

st.set_page_config(page_title="TalkTime App", layout="wide")

# --------------------
# Helpers
# --------------------

def to_seconds(x):
    if pd.isna(x):
        return np.nan
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    s = str(x).strip()
    # number
    try:
        return float(s)
    except:
        pass
    # HH:MM:SS or MM:SS
    parts = s.split(":")
    try:
        parts = [float(p) for p in parts]
    except:
        return np.nan
    if len(parts) == 2:
        m, s = parts
        return m*60 + s
    if len(parts) == 3:
        h, m, s = parts
        return h*3600 + m*60 + s
    return np.nan

def parse_date_best(series):
    d1 = pd.to_datetime(series, errors="coerce", dayfirst=True)
    d2 = pd.to_datetime(series, errors="coerce", dayfirst=False)
    return d1 if d1.notna().sum() >= d2.notna().sum() else d2

def combine_date_time(date_col, time_col):
    d = parse_date_best(date_col)
    t_series = pd.to_datetime(time_col, errors="coerce")
    t = t_series.dt.time if hasattr(t_series, "dt") else pd.NaT
    dt = pd.to_datetime(pd.DataFrame({"d": d.dt.date, "t": t}).astype(str).agg(" ".join, axis=1), errors="coerce")
    try:
        dt_local = pd.to_datetime(dt, errors="coerce").dt.tz_localize(TZ, nonexistent="NaT", ambiguous="NaT")
    except Exception:
        dt_local = pd.NaT
    return dt_local

def date_preset_bounds(preset, custom_range):
    now = pd.Timestamp.now(tz=TZ)
    today = now.date()
    if preset == "Today":
        start_date, end_date = today, today
    elif preset == "Yesterday":
        yday = (now - pd.Timedelta(days=1)).date()
        start_date, end_date = yday, yday
    else:
        if not custom_range or not isinstance(custom_range, tuple) or len(custom_range) != 2:
            return None
        start_date, end_date = custom_range
    return start_date, end_date

def filter_by_date(df, start_date, end_date):
    if "_date_only" not in df.columns:
        return df.iloc[0:0]
    mask = (pd.to_datetime(df["_date_only"]) >= pd.to_datetime(start_date)) & (pd.to_datetime(df["_date_only"]) <= pd.to_datetime(end_date))
    return df[mask].copy()

def agg_summary(df, dims, duration_field):
    res = (
        df.groupby(dims, dropna=False)[duration_field]
          .agg(["count", "sum", "mean", "median"])
          .reset_index()
          .rename(columns={
              "count": "Total Calls",
              "sum": "Total Duration (sec)",
              "mean": "Avg Duration (sec)",
              "median": "Median Duration (sec)"
          })
          .sort_values(["Total Calls","Total Duration (sec)"], ascending=[False, False])
    )
    return res

def download_df(df, filename, label="Download CSV"):
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label, csv, file_name=filename, mime="text/csv")

def clean_str_col(series):
    if series is None:
        return series
    s = series.copy()
    try:
        return s.where(s.isna(), s.astype(str).str.strip())
    except Exception:
        return s

def norm_name(s):
    if pd.isna(s):
        return ""
    s = str(s).lower().strip()
    keep = []
    for ch in s:
        if ch.isalnum():
            keep.append(ch)
        elif ch.isspace():
            keep.append(" ")
    s = "".join(keep)
    s = " ".join(s.split())
    return s

def fuzzy_match_any(name, targets_norm, ratio_cut=0.85):
    from difflib import SequenceMatcher
    n = norm_name(name)
    if not n:
        return False
    for t in targets_norm:
        if not t:
            continue
        if t in n or n in t:
            return True
        t_tokens = t.split()
        if any(tok and tok in n for tok in t_tokens):
            return True
        if SequenceMatcher(None, n, t).ratio() >= ratio_cut:
            return True
    return False

# --------------------
# Teams (fixed lists + fuzzy)
# --------------------
B2C_TARGETS_RAW = [
    "Kamaldeep singh",
    "Ria Arora",
    "ayushman jetlearn",
    "Shujaat Shafqat",
    "Unmesh Kamble",
    "Ziyaulhaq Badr",
    "Visakha",
    "Jay Nayak",
    "Ankush Kumar",
    "Fuzail Saudagar",
    "Aniket Srivastava",
    "Shahbaz Ali",
    "Vikas Jha",
]
MTTEAM_TARGETS_RAW = [
    "AYUSHMAN",
]

B2C_TARGETS = [norm_name(x) for x in B2C_TARGETS_RAW]
MTTEAM_TARGETS = [norm_name(x) for x in MTTEAM_TARGETS_RAW]

# --------------------
# Sidebar
# --------------------

st.title(APP_TITLE)
with st.sidebar:
    st.header("1) Upload")
    file = st.file_uploader("Upload CSV with columns: Date, Time, Caller (Agent), Call Type, Country Name, Call Status, Call Duration", type=["csv"])

    st.header("2) Agent Set")
    team_mode = st.radio("Base selection", ["All agents", "B2C team only"],
                         help="Pick base set here. Use the checkbox below to add MT Team.")
    add_mt = st.checkbox("Include MT Team (AYUSHMAN)", value=False)

    st.header("3) Mode")
    mode = st.radio("Calls to include", ["All calls", "Only calls with duration ≥ threshold"], index=0)
    threshold = st.slider("Threshold (sec)", 10, 300, 60, 5, help="Used when filtering calls by minimum duration.")

    st.header("4) Period (IST)")
    preset = st.radio("Pick a range", ["Today", "Yesterday", "Custom"], index=0)
    custom = None
    if preset == "Custom":
        custom = st.date_input("Custom range (inclusive)", help="Select start and end date (IST).", value=None)

    st.header("5) Filters")
    include_missing = st.checkbox("Include rows with missing values for selected filters", value=True,
                                  help="When ON, rows with blank Agent/Country/Type/Status are kept even if filters are applied.")
    st.caption("Filter pickers appear after upload.")

if not file:
    st.info("Upload your CSV to begin.")
    st.stop()

# --------------------
# Load & Prepare
# --------------------

try:
    df = pd.read_csv(file, low_memory=False)
except Exception as e:
    st.error(f"Failed to read CSV: {e}")
    st.stop()

# Clean key columns
for col in ["Caller", "Country Name", "Call Type", "Call Status"]:
    if col in df.columns:
        df[col] = clean_str_col(df[col])

# Parse duration and dates
df["_duration_sec"] = df["Call Duration"].apply(to_seconds) if "Call Duration" in df.columns else np.nan
df["_date_only"] = parse_date_best(df["Date"]) if "Date" in df.columns else pd.NaT
df["_date_only"] = pd.to_datetime(df["_date_only"]).dt.date

# Optional time for hour visuals
if {"Date","Time"}.issubset(df.columns):
    df["_dt_local"] = combine_date_time(df["Date"], df["Time"])
    df["_hour"] = df["_dt_local"].dt.hour
else:
    df["_dt_local"] = pd.NaT
    df["_hour"] = np.nan

# Sidebar pickers (default ALL)
with st.sidebar:
    if "Caller" in df.columns:
        agents = sorted(df["Caller"].dropna().astype(str).unique().tolist())
        sel_agents = st.multiselect("Agent(s)", agents, default=agents)
    else:
        sel_agents = None

    if "Country Name" in df.columns:
        countries = sorted(df["Country Name"].dropna().astype(str).unique().tolist())
        sel_countries = st.multiselect("Country(ies)", countries, default=countries)
    else:
        sel_countries = None

    if "Call Type" in df.columns:
        call_types = sorted(df["Call Type"].dropna().astype(str).unique().tolist())
        sel_types = st.multiselect("Call Type(s) (optional)", call_types, default=call_types)
    else:
        sel_types = None

    if "Call Status" in df.columns:
        statuses = sorted(df["Call Status"].dropna().astype(str).unique().tolist())
        sel_status = st.multiselect("Call Status", statuses, default=statuses)
    else:
        sel_status = None

# Date filter (by Date only)
bounds = date_preset_bounds(preset, custom)
if bounds is not None:
    start_date, end_date = bounds
    df_f = filter_by_date(df, start_date, end_date)
else:
    df_f = df.copy()

# Build team masks
def mask_for_targets(frame, col, targets_norm):
    if col not in frame.columns:
        return pd.Series(False, index=frame.index)
    return frame[col].apply(lambda x: fuzzy_match_any(x, targets_norm))

b2c_mask = mask_for_targets(df_f, "Caller", B2C_TARGETS)
mt_mask = mask_for_targets(df_f, "Caller", MTTEAM_TARGETS)

# Apply base team selection
if team_mode == "B2C team only":
    team_mask = b2c_mask.copy()
else:  # All agents
    team_mask = pd.Series(True, index=df_f.index)

# Additive MT Team checkbox
if add_mt:
    team_mask = team_mask | mt_mask

# Respect include_missing setting for Agent column
if include_missing and "Caller" in df_f.columns:
    team_mask = team_mask | df_f["Caller"].isna()

df_f = df_f[team_mask].copy()

# Generic filters — preserve NaN when include_missing=True
def _apply_filter(frame, col, selections):
    if selections is None or col not in frame.columns:
        return frame
    if len(selections) == 0:
        return frame
    if include_missing:
        return frame[frame[col].astype(str).isin(selections) | frame[col].isna()]
    else:
        return frame[frame[col].astype(str).isin(selections)]

df_f = _apply_filter(df_f, "Caller", sel_agents)
df_f = _apply_filter(df_f, "Country Name", sel_countries)
df_f = _apply_filter(df_f, "Call Type", sel_types)
df_f = _apply_filter(df_f, "Call Status", sel_status)

# Mode filter
if mode.startswith("Only calls"):
    df_view = df_f[df_f["_duration_sec"] >= float(threshold)].copy()
else:
    df_view = df_f.copy()

# --------------------
# KPIs
# --------------------
st.subheader("Overview")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Calls", f"{len(df_view):,}")
k2.metric("Avg Duration (sec)", f"{df_view['_duration_sec'].mean():,.1f}" if df_view["_duration_sec"].notna().any() else "NA")
k3.metric("Median Duration (sec)", f"{df_view['_duration_sec'].median():,.1f}" if df_view["_duration_sec"].notna().any() else "NA")
k4.metric("Agents", df_view["Caller"].nunique() if "Caller" in df_view.columns else 0)
st.caption(f"Base: **{team_mode}** | +MT Team: **{add_mt}** | Mode: **{mode}** | Threshold: **{threshold}s** | Range: **{preset}** (IST)")

# --------------------
# Tabs
# --------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "Agent-wise (Agent)", "Country-wise", "Agent × Country", "24h Engagement"
])

with tab1:
    st.markdown("### Agent-wise — Total number of calls and durations")
    if "Caller" in df_view.columns:
        agg = agg_summary(df_view, ["Caller"], "_duration_sec")
        st.dataframe(agg, use_container_width=True)
        download_df(agg, "agent_wise_calls.csv")
        chart = alt.Chart(agg).mark_bar().encode(
            x=alt.X("Caller:N", sort="-y", title="Agent"),
            y=alt.Y("Total Calls:Q"),
            tooltip=["Caller","Total Calls","Total Duration (sec)","Avg Duration (sec)","Median Duration (sec)"]
        ).properties(height=360).interactive()
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Column 'Caller' (Agent) missing.")

with tab2:
    st.markdown("### Country-wise — Total number of calls and durations")
    if "Country Name" in df_view.columns:
        agg = agg_summary(df_view, ["Country Name"], "_duration_sec")
        st.dataframe(agg, use_container_width=True)
        download_df(agg, "country_wise_calls.csv")
        chart = alt.Chart(agg).mark_bar().encode(
            x=alt.X("Country Name:N", sort="-y", title="Country"),
            y=alt.Y("Total Calls:Q"),
            tooltip=["Country Name","Total Calls","Total Duration (sec)","Avg Duration (sec)","Median Duration (sec)"]
        ).properties(height=360).interactive()
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Column 'Country Name' missing.")

with tab3:
    st.markdown("### Agent × Country — Matrix")
    if {"Caller","Country Name"}.issubset(df_view.columns):
        agg = agg_summary(df_view, ["Caller","Country Name"], "_duration_sec")
        st.dataframe(agg, use_container_width=True)
        download_df(agg, "agent_country_matrix.csv")
        chart = alt.Chart(agg).mark_bar().encode(
            x=alt.X("Caller:N", sort=alt.SortField("Total Calls", order="descending"), title="Agent"),
            y=alt.Y("Total Calls:Q"),
            color=alt.Color("Country Name:N", title="Country"),
            tooltip=["Caller","Country Name","Total Calls","Total Duration (sec)"]
        ).properties(height=380).interactive()
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Need 'Caller' (Agent) and 'Country Name'.")

with tab4:
    st.markdown("### 24h Engagement — When do agents attempt calls, and for which country?")
    df_time = df_f.dropna(subset=["_hour"]) if "_hour" in df_f.columns else pd.DataFrame(columns=df_f.columns)
    if not df_time.empty and df_time["_hour"].notna().any():
        attempts = (df_time
                    .groupby("_hour", dropna=False)
                    .size().reset_index(name="Attempts").rename(columns={"_hour":"Hour"}))
        c1, c2 = st.columns(2)
        with c1:
            st.dataframe(attempts.sort_values("Hour"), use_container_width=True)
            download_df(attempts.sort_values("Hour"), "attempts_by_hour.csv")
        with c2:
            chart = alt.Chart(attempts).mark_circle().encode(
                x=alt.X("Hour:O", title="Hour (0–23, IST)"),
                y=alt.Y("Attempts:Q"),
                size=alt.Size("Attempts:Q", legend=None),
                tooltip=["Hour:O","Attempts:Q"]
            ).properties(height=340).interactive()
            st.altair_chart(chart, use_container_width=True)

        st.divider()
        st.markdown("**Bubble: Hour vs Country (Attempts)**")
        if "Country Name" in df_time.columns:
            a2 = (df_time.groupby(["_hour","Country Name"], dropna=False).size()
                    .reset_index(name="Attempts").rename(columns={"_hour":"Hour"}))
            bubble = alt.Chart(a2).mark_circle().encode(
                x=alt.X("Hour:O"),
                y=alt.Y("Country Name:N", title="Country"),
                size=alt.Size("Attempts:Q", legend=None),
                tooltip=["Hour:O","Country Name:N","Attempts:Q"]
            ).properties(height=420).interactive()
            st.altair_chart(bubble, use_container_width=True)
            download_df(a2.sort_values(["Country Name","Hour"]), "hour_country_bubble.csv")

        st.divider()
        st.markdown("**Heatmap: Agent × Hour (Attempts)**")
        if "Caller" in df_time.columns:
            hh = (df_time.groupby(["Caller","_hour"], dropna=False).size()
                    .reset_index(name="Attempts").rename(columns={"_hour":"Hour"}))
            heat = alt.Chart(hh).mark_rect().encode(
                x=alt.X("Hour:O"),
                y=alt.Y("Caller:N", title="Agent"),
                color=alt.Color("Attempts:Q"),
                tooltip=["Caller","Hour","Attempts"]
            ).properties(height=420).interactive()
            st.altair_chart(heat, use_container_width=True)
            download_df(hh.sort_values(["Caller","Hour"]), "agent_hour_heatmap.csv")
    else:
        st.info("No valid Time values to compute 24h engagement; counts/tables still use Date-based logic.")

st.caption("v3.6: Radio for base set (All / B2C), plus additive checkbox 'Include MT Team (AYUSHMAN)'. Date-only counting, include-missing, robust duration parsing.")
