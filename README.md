# Event Analytics Dashboard

A professional Streamlit dashboard that connects to a Google Sheet and visualizes hackathon/event statistics with interactive Plotly charts.

## Features

- **Google Sheets integration** — Connect via Service Account (Sheet ID + credentials JSON)
- **Event selector** — Multi-select one or more initiatives to view combined or single-event stats
- **KPI cards** — Total Registrations, Submissions, Teams, Page Visits
- **Charts** — Daily Registrations (line), Gender & Occupation (pie), Country, State & City (bar)
- **JSON parsing** — Automatically parses and aggregates JSON columns (Gender, Daily Registrations, Country, State, City, Occupation)
- **Caching** — Sheet data cached for 5 minutes for better performance
- **RBAC & login** — Role-based access: **admin** (full access, can change sheet/credentials and connect), **viewer** (read-only dashboard with default sheet)

## Project structure

```
project/
    app.py              # Streamlit dashboard (use streamlit run or python app.py)
    server.py           # Flask + portal UI (used by run.py)
    auth.py             # RBAC: users, roles, login
    run.py              # Start Flask on port 3005 — production (python run.py)
    sheets_connector.py # Google Sheets connection (gspread + service account)
    utils.py            # JSON parsing and aggregation helpers
    .streamlit/
        config.toml    # Server port 3005, headless
    requirements.txt
    README.md
    credentials.example.json  # Example service account key structure (copy to credentials.json)
```

## Setup

### 1. Create a virtual environment (recommended)

```bash
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # macOS/Linux
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Google Sheets API (Service Account)

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project (or select one) and enable **Google Sheets API** and **Google Drive API**.
3. Create a **Service Account** (IAM & Admin → Service Accounts → Create).
4. Create a key (JSON) and download it.
5. Save the JSON file as `credentials.json` in the project root (or set the path in the app sidebar). Use `credentials.example.json` as a reference for the expected structure.
6. Share your Google Sheet with the service account **email** (e.g. `xxx@xxx.iam.gserviceaccount.com`) with **Viewer** access.

### 4. Sheet format

Your sheet should have a first row of headers and at least these columns (names must match):

- Initiative Name  
- Initiative URL  
- Created At, Created By  
- Registration End Date, Submission Start Date, Submission End Date  
- Registration Count, Submission Count, Teams Count, Page Visits  
- Gender Distribution  
- Daily Registrations  
- Country, State, City  
- Occupation  

These columns should contain valid JSON objects, e.g.:

- **Gender Distribution:** `{"Male": 10, "Female": 5, "Other": 2}`
- **Daily Registrations:** `{"2024-01-01": 3, "2024-01-02": 7}`
- **Country:** `{"India": 20, "USA": 5}`

## Login (RBAC)

The app shows a login page first. Default users (change in production):



**Changing a password**

1. Generate the hash for your new password:
   ```bash
   python auth.py YourNewPassword
   ```
   (Or: `python -c "from auth import get_password_hash; print(get_password_hash('YourNewPassword'))"`)
2. Open `auth.py` and find `USER_STORE`.
3. Replace the `password_hash` for the user (e.g. `"admin"` or `"viewer"`) with the printed hash.
4. Save the file; the new password applies on next login.

To add users or change the salt, edit `auth.py` (USER_STORE and AUTH_SALT). Use a strong salt and hashed passwords in production.

## Run the app

Two entry points:

| Command | What it starts | Use when |
|--------|----------------|----------|
| `python run.py` | **Flask** app (`server.py`) on port **3005** — portal JWT, HTML UI | Production behind Hack2skill Central Data Intelligence / nginx |
| `streamlit run app.py` or `python app.py` | **Streamlit** dashboard on **3005** (see `.streamlit/config.toml`) | Legacy Streamlit UI only |

Do **not** rely on `python app.py` without this repo’s bootstrap: older setups would show `missing ScriptRunContext` because Streamlit must own the process. After the bootstrap, `python app.py` is equivalent to `streamlit run app.py`.

```bash
# Portal-integrated web app (recommended for h2s.tech / proxy)
python run.py

# Streamlit version (same data layer, different UI)
streamlit run app.py
# or
python app.py
```

Then open **http://localhost:3005** in your browser.

Then:

1. Enter your **Google Sheet ID** in the sidebar (from the sheet URL: `https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`).
2. Click **Connect**.
3. Select one or more events from **Event selector**.
4. View KPIs and charts on the main page.

## Tech stack

- **Python**  
- **Streamlit** — UI  
- **Pandas** — Data handling  
- **Plotly** — Charts  
- **gspread** + **google-auth** — Google Sheets API (service account)

## License

Use and modify as needed for your organization.
