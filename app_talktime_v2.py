
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from io import BytesIO

APP_TITLE = "📞 TalkTime App — v2 (JetLearn)"
TZ = "Asia/Kolkata"
DEFAULT_THRESHOLD = 60

st.set_page_config(page_title="TalkTime App", layout="wide")

# -------------------------------
# Helpers
# -------------------------------

def to_seconds(x):
    """Parse seconds or 'HH:MM:SS'/'MM:SS' strings to seconds."""
    if pd.isna(x):
        return np.nan
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    s = str(x).strip()
    # Try numeric
    try:
        return float(s)
    except:
        pass
    parts = s.split(":")
    try:
        parts = [float(p) for p in parts]
    except:
        return np.nan
    if len(parts) == 2:
        m, s = parts
        return m * 60 + s
    if len(parts) == 3:
        h, m, s = parts
        return h * 3600 + m * 60 + s
    return np.nan

def combine_date_time(date_col, time_col):
    """Combine separate Date and Time columns into timezone-aware datetime."""
    dt_date = pd.to_datetime(date_col, errors="coerce", dayfirst=False)
    # Time may be HH:MM or HH:MM:SS or AM/PM
    dt_time = pd.to_datetime(time_col, errors="coerce").dt.time
    # Fallback if time parsing fails: try manual
    mask_bad = dt_time.isna() & time_col.notna()
    if mask_bad.any():
        parsed_manual = []
        for t in time_col[mask_bad].astype(str):
            t2 = pd.NaT
            try:
                # Try to parse as string time (24h or 12h)
                t2 = pd.to_datetime(t, format="%H:%M", errors="coerce")
                if pd.isna(t2):
                    t2 = pd.to_datetime(t, format="%H:%M:%S", errors="coerce")
                if pd.isna(t2):
                    t2 = pd.to_datetime(t, errors="coerce")
                parsed_manual.append(t2.time() if not pd.isna(t2) else pd.NaT)
            except:
                parsed_manual.append(pd.NaT)
        dt_time.loc[mask_bad] = parsed_manual
    # Build naive datetime then localize
    dt = pd.to_datetime(
        pd.DataFrame({"d": dt_date.dt.date, "t": dt_time}).astype(str).agg(" ".join, axis=1),
        errors="coerce"
    )
    # Localize to IST; assume given local
    try:
        dt_local = pd.to_datetime(dt).dt.tz_localize(TZ, nonexistent="NaT", ambiguous="NaT")
    except:
        dt_local = pd.to_datetime(dt, errors="coerce")
        dt_local = dt_local.dt.tz_localize(TZ, nonexistent="NaT", ambiguous="NaT")
    return dt_local

def filt_date_preset(df_dt, preset, custom_range):
    if preset == "Today":
        start = pd.Timestamp.today(tz=TZ).normalize()
        end = start + pd.Timedelta(days=1)
    elif preset == "Yesterday":
        end = pd.Timestamp.today(tz=TZ).normalize()
        start = end - pd.Timedelta(days=1)
    else:  # Custom
        if not custom_range or not isinstance(custom_range, tuple) or len(custom_range) != 2:
            return df_dt
        s, e = custom_range
        start = pd.Timestamp(s, tz=TZ)
        end = pd.Timestamp(e, tz=TZ) + pd.Timedelta(days=1)
    return df_dt[(df_dt["_dt_local"] >= start) & (df_dt["_dt_local"] < end)]

def kpi_card(label, value, helptext=None):
    st.metric(label, value)
    if helptext:
        st.caption(helptext)

def download_df(df, filename, label="Download CSV"):
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label, csv, file_name=filename, mime="text/csv")

def aggregate(df, dims, duration_field):
    agg = (
        df.groupby(dims, dropna=False)[duration_field]
        .agg(["count", "sum", "mean", "median"])
        .reset_index()
        .rename(columns={"count": "Call Count", "sum": "Total Duration (sec)",
                         "mean": "Avg Duration (sec)", "median": "Median Duration (sec)"})
        .sort_values("Total Duration (sec)", ascending=False)
    )
    return agg

def section_header(title, icon=""):
    st.markdown(f"### {icon} {title}" if icon else f"### {title}")

# -------------------------------
# Sidebar
# -------------------------------

st.title(APP_TITLE)

with st.sidebar:
    st.header("1) Upload")
    file = st.file_uploader("Upload CSV with columns: Date, Time, Caller, To Name, Call Type, Country Name, Call Status, Call Duration", type=["csv"])

    st.header("2) Mode")
    mode = st.radio(
        "Counting Mode",
        ["Talktime (>= threshold sec)", "Overall (all calls)"],
        help="Talktime counts only calls with duration >= threshold (default 60s). Overall counts all calls."
    )
    threshold = st.slider("Talktime threshold (sec)", 10, 300, DEFAULT_THRESHOLD, 5)

    st.header("3) Date Range")
    preset = st.radio("Choose Period", ["Today", "Yesterday", "Custom"])
    custom = None
    if preset == "Custom":
        st.caption("Pick inclusive start and end dates (IST).")
        custom = st.date_input("Custom Range", help="Select start and end date (IST).", value=None)

    st.header("4) Filters")
    st.caption("Filters will appear after upload.")

if not file:
    st.info("Upload your CSV to begin.")
    st.stop()

# -------------------------------
# Load & Prepare
# -------------------------------

try:
    df = pd.read_csv(file, low_memory=False)
except Exception as e:
    st.error(f"Failed to read CSV: {e}")
    st.stop()

expected = ["Date", "Time", "Caller", "To Name", "Call Type", "Country Name", "Call Status", "Call Duration"]
missing = [c for c in expected if c not in df.columns]
if missing:
    st.warning(f"Missing expected columns: {', '.join(missing)}. The app may not render all views.")

# Normalize fields
df["_duration_sec"] = df["Call Duration"].apply(to_seconds) if "Call Duration" in df.columns else np.nan
if "Date" in df.columns and "Time" in df.columns:
    df["_dt_local"] = combine_date_time(df["Date"], df["Time"])
else:
    df["_dt_local"] = pd.NaT

# Derived fields
if "_dt_local" in df.columns:
    df["_date"] = df["_dt_local"].dt.date
    df["_hour"] = df["_dt_local"].dt.hour

# Sidebar filters (after load)
with st.sidebar:
    # Caller filter
    if "Caller" in df.columns:
        callers = sorted(df["Caller"].dropna().astype(str).unique().tolist())
        sel_callers = st.multiselect("Filter: Academic Counsellor (Caller)", callers, default=callers[: min(10, len(callers))])
    else:
        sel_callers = None

    # Country filter
    if "Country Name" in df.columns:
        countries = sorted(df["Country Name"].dropna().astype(str).unique().tolist())
        sel_countries = st.multiselect("Filter: Country", countries, default=countries[: min(10, len(countries))])
    else:
        sel_countries = None

    # Call Type filter
    if "Call Type" in df.columns:
        types_ = sorted(df["Call Type"].dropna().astype(str).unique().tolist())
        sel_types = st.multiselect("Filter: Call Type", types_, default=types_[: min(10, len(types_))])
    else:
        sel_types = None

    # Call Status filter
    if "Call Status" in df.columns:
        statuses = sorted(df["Call Status"].dropna().astype(str).unique().tolist())
        sel_status = st.multiselect("Filter: Call Status", statuses, default=statuses[: min(10, len(statuses))])
    else:
        sel_status = None

# Apply date preset filter
df_f = df.dropna(subset=["_dt_local"]).copy()
df_f = filt_date_preset(df_f, preset, custom)

# Apply other filters
if sel_callers is not None and len(sel_callers) > 0:
    df_f = df_f[df_f["Caller"].astype(str).isin(sel_callers)]
if sel_countries is not None and len(sel_countries) > 0:
    df_f = df_f[df_f["Country Name"].astype(str).isin(sel_countries)]
if sel_types is not None and len(sel_types) > 0:
    df_f = df_f[df_f["Call Type"].astype(str).isin(sel_types)]
if sel_status is not None and len(sel_status) > 0:
    df_f = df_f[df_f["Call Status"].astype(str).isin(sel_status)]

# Apply mode logic
if mode.startswith("Talktime"):
    df_rules = df_f[df_f["_duration_sec"] >= float(threshold)].copy()
else:
    df_rules = df_f.copy()

# -------------------------------
# Overview KPIs
# -------------------------------

st.subheader("Overview")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Calls", f"{len(df_rules):,}")
k2.metric("Avg Duration (sec)", f"{df_rules['_duration_sec'].mean():,.1f}" if df_rules["_duration_sec"].notna().any() else "NA")
k3.metric("Median Duration (sec)", f"{df_rules['_duration_sec'].median():,.1f}" if df_rules["_duration_sec"].notna().any() else "NA")
k4.metric("Unique Callers", df_rules["Caller"].nunique() if "Caller" in df_rules.columns else 0)

st.caption("Mode: **{}** | Threshold: **{} sec** | Period: **{}**".format(mode, threshold, preset))

# -------------------------------
# Tabs
# -------------------------------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Agent-wise", "Country-wise", "Agent × Country", "24h Horizon", "Variable Profiles", "Explorer (Choose Dims)"
])

with tab1:
    section_header("Agent-wise Talktime Detail", "🧑‍💼")
    if "Caller" in df_rules.columns:
        agg = aggregate(df_rules, ["Caller"], "_duration_sec")
        st.dataframe(agg, use_container_width=True)
        download_df(agg, "agent_wise.csv")
        # Chart
        chart = alt.Chart(agg).mark_bar().encode(
            x=alt.X("Caller:N", sort="-y", title="Caller (Academic Counsellor)"),
            y=alt.Y("Total Duration (sec):Q"),
            tooltip=["Caller", "Call Count", "Total Duration (sec)", "Avg Duration (sec)", "Median Duration (sec)"]
        ).properties(height=350).interactive()
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Column 'Caller' missing.")

with tab2:
    section_header("Country-wise Talktime Detail", "🌏")
    if "Country Name" in df_rules.columns:
        agg = aggregate(df_rules, ["Country Name"], "_duration_sec")
        st.dataframe(agg, use_container_width=True)
        download_df(agg, "country_wise.csv")
        chart = alt.Chart(agg).mark_bar().encode(
            x=alt.X("Country Name:N", sort="-y"),
            y=alt.Y("Total Duration (sec):Q"),
            tooltip=["Country Name", "Call Count", "Total Duration (sec)", "Avg Duration (sec)", "Median Duration (sec)"]
        ).properties(height=350).interactive()
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Column 'Country Name' missing.")

with tab3:
    section_header("Agent × Country Matrix", "🧩")
    if {"Caller", "Country Name"}.issubset(df_rules.columns):
        agg = aggregate(df_rules, ["Caller", "Country Name"], "_duration_sec")
        st.dataframe(agg, use_container_width=True)
        download_df(agg, "agent_country.csv")
        # Stacked bar by country
        chart = alt.Chart(agg).mark_bar().encode(
            x=alt.X("Caller:N", title="Caller", sort=alt.SortField("Total Duration (sec)", order="descending")),
            y=alt.Y("Total Duration (sec):Q"),
            color=alt.Color("Country Name:N", title="Country"),
            tooltip=["Caller", "Country Name", "Call Count", "Total Duration (sec)"]
        ).properties(height=380).interactive()
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Need 'Caller' and 'Country Name'.")

with tab4:
    section_header("24h Horizon — Attempts by Hour (IST)", "⏱️")
    if "_hour" in df_f.columns and df_f["_hour"].notna().any():
        attempts = (
            df_f.groupby("_hour")
            .size()
            .reset_index(name="Attempts")
            .rename(columns={"_hour": "Hour"})
            .sort_values("Hour")
        )
        c1, c2 = st.columns([1,1])
        with c1:
            st.dataframe(attempts, use_container_width=True)
            download_df(attempts, "attempts_by_hour.csv")
        with c2:
            chart = alt.Chart(attempts).mark_circle().encode(
                x=alt.X("Hour:O", title="Hour of Day (0–23)"),
                y=alt.Y("Attempts:Q"),
                size=alt.Size("Attempts:Q", legend=None),
                tooltip=["Hour:O", "Attempts:Q"]
            ).properties(height=350).interactive()
            st.altair_chart(chart, use_container_width=True)

        st.divider()
        st.markdown("**Heatmap: Caller × Hour (Attempts)**")
        if "Caller" in df_f.columns:
            hh = (df_f.groupby(["Caller", "_hour"]).size().reset_index(name="Attempts")
                    .rename(columns={"_hour": "Hour"}))
            heat = alt.Chart(hh).mark_rect().encode(
                x=alt.X("Hour:O"),
                y=alt.Y("Caller:N"),
                color=alt.Color("Attempts:Q"),
                tooltip=["Caller", "Hour", "Attempts"]
            ).properties(height=400).interactive()
            st.altair_chart(heat, use_container_width=True)
            download_df(hh.sort_values(["Caller", "Hour"]), "caller_hour_heatmap.csv")
        else:
            st.info("Column 'Caller' missing for heatmap.")
    else:
        st.info("No valid Date/Time to compute hour distribution.")

with tab5:
    section_header("Variable Profiles", "📊")
    cols_present = [c for c in ["Call Type", "Call Status", "To Name"] if c in df_rules.columns]
    if not cols_present:
        st.info("No profile variables available.")
    else:
        for c in cols_present:
            st.markdown(f"**{c}**")
            agg = aggregate(df_rules, [c], "_duration_sec")
            st.dataframe(agg, use_container_width=True)
            download_df(agg, f"profile_{c.replace(' ', '_').lower()}.csv")
            chart = alt.Chart(agg).mark_bar().encode(
                x=alt.X(f"{c}:N", sort="-y"),
                y=alt.Y("Total Duration (sec):Q"),
                tooltip=[c, "Call Count", "Total Duration (sec)"]
            ).properties(height=300).interactive()
            st.altair_chart(chart, use_container_width=True)
            st.markdown("---")

with tab6:
    section_header("Explorer — Choose up to 2 dimensions", "🧭")
    dims_all = [c for c in ["Caller", "Country Name", "Call Type", "Call Status", "To Name"] if c in df_rules.columns]
    if len(dims_all) == 0:
        st.info("No dimensions available.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            dim1 = st.selectbox("Dimension 1", dims_all, index=0, key="dim1")
        with c2:
            dims2_opts = ["(none)"] + [d for d in dims_all if d != dim1]
            dim2 = st.selectbox("Dimension 2 (optional)", dims2_opts, index=0, key="dim2")
        dims = [dim1] + ([] if dim2 == "(none)" else [dim2])
        agg = aggregate(df_rules, dims, "_duration_sec")
        st.dataframe(agg, use_container_width=True)
        download_df(agg, "explorer_agg.csv")
        # Chart
        if len(dims) == 1:
            chart = alt.Chart(agg).mark_bar().encode(
                x=alt.X(f"{dim1}:N", sort="-y"),
                y=alt.Y("Total Duration (sec):Q"),
                tooltip=dims + ["Call Count", "Total Duration (sec)"]
            ).properties(height=380).interactive()
        else:
            chart = alt.Chart(agg).mark_bar().encode(
                x=alt.X(f"{dim1}:N", sort="-y"),
                y=alt.Y("Total Duration (sec):Q"),
                color=alt.Color(f"{dim2}:N"),
                tooltip=dims + ["Call Count", "Total Duration (sec)"]
            ).properties(height=380).interactive()
        st.altair_chart(chart, use_container_width=True)

st.caption("Tip: Use the sidebar to switch **Talktime / Overall**, change **threshold**, and pick **Today / Yesterday / Custom** periods.")
