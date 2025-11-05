
# TalkTime App — v3

Tailored to columns:
- Date, Time, Caller (Agent), To Name (ignored), Call Type, Country Name, Call Status, Call Duration

## Features
- **Presets:** Today / Yesterday / Custom (IST-based)
- **Mode:** All calls OR only calls with duration ≥ threshold (default 60s)
- **Filters:** Agent(s), Country(ies), Call Type(s), Call Status
- **Tabs:**
  - Agent-wise counts & durations (table + bar)
  - Country-wise counts & durations (table + bar)
  - Agent × Country matrix (stacked bar + table)
  - 24h Engagement: attempts by hour (bubble), Hour × Country (bubble), Agent × Hour (heatmap)

## Run
```bash
pip install -r requirements.txt
streamlit run app_talktime_v3.py
```

## Deploy
Push to GitHub and deploy on Streamlit Cloud.
