
# TalkTime App (Streamlit)

An interactive dashboard to analyze agent talk time from your call activity feed (CSV).

## Features
- Agent-wise talktime summary
- Country-wise talktime summary
- Agent × Country matrix
- 24-hour bubble chart of call attempts (local time Asia/Kolkata)
- **Mode toggle**: 
  - *Talktime*: only calls with duration ≥ threshold seconds (default 60s)
  - *Overall*: consider all calls
- Robust column mapping (sidebar) for Agent, Country, Duration, and Start Time.
- CSV downloads for every view.

## Expected Columns
You can map any of your column names in the sidebar. Typical defaults the app will look for:
- **Agent/User**: `Owner`, `Agent`, `User`, `Student/Academic Counsellor`, `Assigned To`
- **Country**: `Country`, `Country/Region`
- **Duration**: `Call Duration`, `Duration`, `Talk Time` (accepts seconds or `HH:MM:SS` / `MM:SS` strings)
- **Start Time**: `Start Time`, `Call Start Time`, `Created At`, `Timestamp`

## Local Run
```bash
pip install -r requirements.txt
streamlit run app_talktime.py
```

## Deploy on Streamlit Cloud
1. Push `app_talktime.py` and `requirements.txt` (and optionally this README) to a GitHub repo.
2. Create a new Streamlit Cloud app from that repo.
3. Upload your CSV via the sidebar.

## Notes
- Timezone is normalized to **Asia/Kolkata** for the 24‑hour chart.
- If your timestamps are UTC, the app converts them. If not, they will be localized to Asia/Kolkata.
