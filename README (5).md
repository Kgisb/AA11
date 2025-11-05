
# TalkTime App — v2 (JetLearn)

Improved UI tailored to columns: `Date, Time, Caller, To Name, Call Type, Country Name, Call Status, Call Duration`.

## Key Upgrades
- **Date presets:** Today / Yesterday / Custom range (IST).
- **Mode toggle:** Talktime (>= threshold sec) vs Overall.
- **Agent-wise, Country-wise, Agent×Country** tabs with charts + CSV downloads.
- **24h Horizon:** Attempts by hour bubble + Caller×Hour heatmap (IST).
- **Variable Profiles:** Call Type, Call Status, To Name summaries.
- **Explorer:** Pick up to two dimensions for quick pivots and charts.

## Run Locally
```bash
pip install -r requirements.txt
streamlit run app_talktime_v2.py
```

## Deploy
Push `app_talktime_v2.py` + `requirements.txt` + this README to GitHub and deploy on Streamlit Cloud.
