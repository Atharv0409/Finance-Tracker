# Finance Tracker

A simple Flask-based personal finance tracker with:

- login-protected dashboard
- income and expense tracking
- charts for totals and monthly breakdowns
- in-page warning and delete confirmation modals

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5000`.

## Deploy on Render

This project is prepared for Render with `render.yaml`.

Set these environment variables in Render:

- `FINANCE_TRACKER_SECRET_KEY`
- `FINANCE_TRACKER_USERNAME`
- `FINANCE_TRACKER_PASSWORD`

After deployment, Render will give the app a permanent public URL.
