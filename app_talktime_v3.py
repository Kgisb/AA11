
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

APP_TITLE = "📞 TalkTime App — v3 (Agent & Country Analytics)"
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

def combine_date_time(date_col, time_col):
    d = pd.to_datetime(date_col, errors="coerce", dayfirst=False)
    # attempt parsing time flexibly
    t_series = pd.to_datetime(time_col, errors="coerce")
    # If parsed as full datetime, take .dt.time
    if isinstance(t_series, pd.Series) and hasattr(t_series.dt, "time"):
        t = t_series.dt.time
    else:
        t = pd.NaT
    # build naive datetime str then localize
    dt = pd.to_datetime(pd.DataFrame({"d": d.dt.date, "t": t}).astype(str).agg(" ".join, axis=1), errors="coerce")
    dt_local = pd.to_datetime(dt, errors="coerce").dt.tz_localize(TZ, nonexistent="NaT", ambiguous="NaT")
    return dt_local

def preset_filter(df, preset, custom_range):
    now = pd.Timestamp.now(tz=TZ)
    today_start = now.normalize()
    if preset == "Today":
        start, end = today_start, today_start + pd.Timedelta(days=1)
    elif preset == "Yesterday":
        end = today_start
        start = end - pd.Timedelta(days=1)
    else:
        if not custom_range or not isinstance(custom_range, tuple) or len(custom_range) != 2:
            return df
        s, e = custom_range
        start = pd.Timestamp(s, tz=TZ)
        end = pd.Timestamp(e, tz=TZ) + pd.Timedelta(days=1)
    return df[(df["_dt_local"] >= start) & (df["_dt_local"] < end)]

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

# --------------------
# Sidebar
# --------------------

st.title(APP_TITLE)
with st.sidebar:
    st.header("1) Upload")
    file = st.file_uploader("Upload CSV with columns: Date, Time, Caller (Agent), To Name (ignored), Call Type, Country Name, Call Status, Call Duration", type=["csv"])

    st.header("2) Mode")
    mode = st.radio("Calls to include", ["All calls", "Only calls with duration ≥ threshold"], index=0)
    threshold = st.slider("Threshold (sec)", 10, 300, 60, 5, help="Used when filtering calls by minimum duration.")

    st.header("3) Period")
    preset = st.radio("Pick a range", ["Today", "Yesterday", "Custom"], index=0, help="Based on IST (Asia/Kolkata).")
    custom = None
    if preset == "Custom":
        custom = st.date_input("Custom range (inclusive)", help="Select start and end date (IST).", value=None)

    st.header("4) Filters")
    st.caption("More filters appear after upload.")

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

expected = ["Date", "Time", "Caller", "To Name", "Call Type", "Country Name", "Call Status", "Call Duration"]
missing = [c for c in expected if c not in df.columns]
if missing:
    st.warning(f"Missing expected columns: {', '.join(missing)}.")

# Mark irrelevant
irrelevant_cols = ["To Name"]

# Parse duration & time
df["_duration_sec"] = df["Call Duration"].apply(to_seconds) if "Call Duration" in df.columns else np.nan
df["_dt_local"] = combine_date_time(df["Date"], df["Time"]) if {"Date","Time"}.issubset(df.columns) else pd.NaT

# Derived
df["_hour"] = df["_dt_local"].dt.hour if "_dt_local" in df.columns else np.nan

# Sidebar filters
with st.sidebar:
    # Agent (Caller)
    if "Caller" in df.columns:
        agents = sorted(df["Caller"].dropna().astype(str).unique().tolist())
        sel_agents = st.multiselect("Agent(s)", agents, default=agents[: min(10, len(agents))])
    else:
        sel_agents = None

    # Country
    if "Country Name" in df.columns:
        countries = sorted(df["Country Name"].dropna().astype(str).unique().tolist())
        sel_countries = st.multiselect("Country(ies)", countries, default=countries[: min(10, len(countries))])
    else:
        sel_countries = None

    # Call Type (checkbox-like multiselect so you can choose multiple or all)
    if "Call Type" in df.columns:
        call_types = sorted(df["Call Type"].dropna().astype(str).unique().tolist())
        sel_types = st.multiselect("Call Type(s) (optional)", call_types, default=call_types)
    else:
        sel_types = None

    # Call Status
    if "Call Status" in df.columns:
        statuses = sorted(df["Call Status"].dropna().astype(str).unique().tolist())
        sel_status = st.multiselect("Call Status (choose All or subset)", statuses, default=statuses)
    else:
        sel_status = None

# Filter by time window
df_f = df.dropna(subset=["_dt_local"]).copy()
df_f = preset_filter(df_f, preset, custom)

# Apply other filters
if sel_agents is not None and len(sel_agents) > 0:
    df_f = df_f[df_f["Caller"].astype(str).isin(sel_agents)]
if sel_countries is not None and len(sel_countries) > 0:
    df_f = df_f[df_f["Country Name"].astype(str).isin(sel_countries)]
if sel_types is not None and len(sel_types) > 0:
    df_f = df_f[df_f["Call Type"].astype(str).isin(sel_types)]
if sel_status is not None and len(sel_status) > 0:
    df_f = df_f[df_f["Call Status"].astype(str).isin(sel_status)]

# Apply talktime filter if requested
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
st.caption(f"Mode: **{mode}** | Threshold: **{threshold}s** | Period: **{preset}** (IST)")

# --------------------
# Tabs
# --------------------

tab1, tab2, tab3, tab4 = st.tabs([
    "Agent-wise (Caller)", "Country-wise", "Agent × Country", "24h Engagement"
])

with tab1:
    st.markdown("### Agent-wise — Total number of calls and durations")
    if "Caller" in df_view.columns:
        agg = agg_summary(df_view, ["Caller"], "_duration_sec")
        st.dataframe(agg, use_container_width=True)
        download_df(agg, "agent_wise_calls.csv")
        # Chart
        chart = alt.Chart(agg).mark_bar().encode(
            x=alt.X("Caller:N", sort="-y", title="Agent"),
            y=alt.Y("Total Calls:Q"),
            tooltip=["Caller","Total Calls","Total Duration (sec)","Avg Duration (sec)","Median Duration (sec)"]
        ).properties(height=360).interactive()
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Column 'Caller' missing.")

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
        # Stacked bar by country within agent
        chart = alt.Chart(agg).mark_bar().encode(
            x=alt.X("Caller:N", sort=alt.SortField("Total Calls", order="descending"), title="Agent"),
            y=alt.Y("Total Calls:Q"),
            color=alt.Color("Country Name:N", title="Country"),
            tooltip=["Caller","Country Name","Total Calls","Total Duration (sec)"]
        ).properties(height=380).interactive()
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Need 'Caller' and 'Country Name'.")

with tab4:
    st.markdown("### 24h Engagement — When do agents attempt calls, and for which country?")
    if df_f["_hour"].notna().any():
        # attempts are based on filtered df_f (before duration filter)
        attempts = df_f.groupby(["_hour"]).size().reset_index(name="Attempts").rename(columns={"_hour":"Hour"})
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
        if "Country Name" in df_f.columns:
            a2 = (df_f.groupby(["_hour","Country Name"]).size()
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
        if "Caller" in df_f.columns:
            hh = df_f.groupby(["Caller","_hour"]).size().reset_index(name="Attempts").rename(columns={"_hour":"Hour"})
            heat = alt.Chart(hh).mark_rect().encode(
                x=alt.X("Hour:O"),
                y=alt.Y("Caller:N", title="Agent"),
                color=alt.Color("Attempts:Q"),
                tooltip=["Caller","Hour","Attempts"]
            ).properties(height=420).interactive()
            st.altair_chart(heat, use_container_width=True)
            download_df(hh.sort_values(["Caller","Hour"]), "agent_hour_heatmap.csv")
    else:
        st.info("No valid Date/Time to compute 24h engagement.")

st.caption("Notes: 'Caller' is the Agent. 'To Name' is ignored. Use filters to slice by Call Type, Call Status, Country, and Agent. Date logic uses IST (Asia/Kolkata).")
