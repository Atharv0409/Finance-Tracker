import json
import os
import sqlite3
from functools import wraps

from flask import Flask, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("FINANCE_TRACKER_SECRET_KEY", "change-this-secret-key")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
DATABASE_FILE = os.path.join(BASE_DIR, "finance_tracker.db")

# Connect to SQLite
db = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
cursor = db.cursor()

# Create table if not exists
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    category TEXT,
    amount REAL,
    type TEXT CHECK(type IN ('income','expense'))
)
"""
)
db.commit()


def load_credentials():
    default_credentials = {"username": "admin", "password": "admin123"}
    env_username = os.environ.get("FINANCE_TRACKER_USERNAME")
    env_password = os.environ.get("FINANCE_TRACKER_PASSWORD")

    if env_username and env_password:
        return {"username": env_username, "password": env_password}

    if not os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, "w", encoding="utf-8") as file:
            json.dump(default_credentials, file, indent=2)
        return default_credentials

    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as file:
            credentials = json.load(file)
    except (OSError, json.JSONDecodeError):
        return default_credentials

    username = credentials.get("username")
    password = credentials.get("password")

    if not username or not password:
        return default_credentials

    return {"username": username, "password": password}


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapped_view


@app.route("/")
def index():
    if session.get("authenticated"):
        return redirect(url_for("dashboard"))
    return render_template("index.html", error=None)


@app.route("/login", methods=["POST"])
def login():
    credentials = load_credentials()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if username == credentials["username"] and password == credentials["password"]:
        session["authenticated"] = True
        return redirect(url_for("dashboard"))

    return render_template("index.html", error="Incorrect username or password.")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    cursor.execute("SELECT * FROM transactions ORDER BY date ASC")
    transactions = cursor.fetchall()

    cursor.execute("SELECT SUM(amount) FROM transactions WHERE type='income'")
    total_income = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(amount) FROM transactions WHERE type='expense'")
    total_expense = cursor.fetchone()[0] or 0

    savings = total_income - total_expense

    cursor.execute(
        """
        SELECT strftime('%m', date) AS month,
               SUM(CASE WHEN type='income' THEN amount ELSE 0 END) AS income,
               SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) AS expense
        FROM transactions
        GROUP BY month
        ORDER BY month ASC
    """
    )
    monthly_data = cursor.fetchall()

    return render_template(
        "dashboard.html",
        transactions=transactions,
        total_income=total_income,
        total_expense=total_expense,
        savings=savings,
        monthly_data=monthly_data,
    )


@app.route("/add", methods=["POST"])
@login_required
def add_transaction():
    date = request.form["date"]
    category = request.form["category"]
    amount = request.form["amount"]
    type_ = request.form["type"]

    cursor.execute(
        "INSERT INTO transactions (date, category, amount, type) VALUES (?, ?, ?, ?)",
        (date, category, amount, type_),
    )
    db.commit()
    return redirect(url_for("dashboard"))


@app.route("/delete/<int:id>")
@login_required
def delete_transaction(id):
    cursor.execute("DELETE FROM transactions WHERE id=?", (id,))
    db.commit()
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    load_credentials()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
