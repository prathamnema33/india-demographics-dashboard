# India Demographics Dashboard

A Dash and Plotly dashboard for visualizing state and district demographic data in India, with a QueryMate backend for natural-language database questions.

## Setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` and `QueryMate\.env.example` to the corresponding `.env` files, then fill in local credentials.

## Run

```powershell
python app_india_map.py
```
