import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from flask import Flask, redirect, render_template, request, session, url_for
app = Flask(__name__)
app.secret_key = os.environ.get("FINANCE_TRACKER_SECRET_KEY", "change-this-secret-key")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
DATABASE_FILE = os.path.join(BASE_DIR, "finance_tracker.db")
db = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
db.row_factory = sqlite3.Row
cursor = db.cursor()
def ensure_column(table_name, column_name, definition):
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row["name"] for row in cursor.fetchall()}
    if column_name not in existing_columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
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
ensure_column("transactions", "description", "TEXT DEFAULT ''")
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        monthly_limit REAL NOT NULL DEFAULT 0
    )
    """
)
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS bills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        amount REAL NOT NULL DEFAULT 0,
        due_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'upcoming'
    )
    """
)
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        target_amount REAL NOT NULL DEFAULT 0,
        current_amount REAL NOT NULL DEFAULT 0
    )
    """
)
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS investments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        current_value REAL NOT NULL DEFAULT 0,
        cost_basis REAL NOT NULL DEFAULT 0
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
def parse_amount(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
def infer_category(description, type_, fallback):
    if fallback and fallback != "Other":
        return fallback
    text = (description or "").strip().lower()
    if not text:
        return "Salary" if type_ == "income" else "Other"
    category_keywords = {
        "Salary": ["salary", "payroll", "bonus", "freelance", "invoice"],
        "Housing": ["rent", "mortgage", "lease", "property"],
        "Groceries": ["grocery", "supermarket", "mart", "vegetable", "food"],
        "Transport": ["uber", "ola", "fuel", "petrol", "bus", "train", "taxi", "transport"],
        "Entertainment": ["movie", "netflix", "spotify", "concert", "game", "entertainment"],
        "Utilities": ["electric", "water", "gas", "internet", "wifi", "phone", "utility"],
        "Healthcare": ["doctor", "hospital", "medicine", "pharmacy", "health"],
        "Investments": ["mutual fund", "etf", "stock", "sip", "investment", "broker"],
        "Dining": ["restaurant", "cafe", "swiggy", "zomato", "dining", "coffee"],
        "Travel": ["flight", "hotel", "trip", "travel"],
    }
    for category_name, keywords in category_keywords.items():
        if any(keyword in text for keyword in keywords):
            return category_name
    return "Income" if type_ == "income" else "Other"
def get_navigation():
    return [
        {"endpoint": "dashboard", "label": "Dashboard"},
        {"endpoint": "budgets", "label": "Budgets"},
        {"endpoint": "bills", "label": "Bills"},
        {"endpoint": "goals", "label": "Goals"},
        {"endpoint": "investments", "label": "Investments"},
    ]
def get_finance_context():
    today = date.today()
    month_prefix = today.strftime("%Y-%m")
    upcoming_cutoff = (today + timedelta(days=7)).isoformat()
    cursor.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC")
    transactions = cursor.fetchall()
    cursor.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM transactions WHERE type='income'")
    total_income = cursor.fetchone()["total"]
    cursor.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM transactions WHERE type='expense'")
    total_expense = cursor.fetchone()["total"]
    savings = total_income - total_expense
    cursor.execute(
        """
        SELECT strftime('%Y-%m', date) AS month,
               SUM(CASE WHEN type='income' THEN amount ELSE 0 END) AS income,
               SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) AS expense
        FROM transactions
        GROUP BY month
        ORDER BY month ASC
        """
    )
    monthly_data = [dict(row) for row in cursor.fetchall()]
    monthly_savings = [
        {
            "month": row["month"],
            "income": row["income"] or 0,
            "expense": row["expense"] or 0,
            "savings": (row["income"] or 0) - (row["expense"] or 0),
        }
        for row in monthly_data
    ]
    cursor.execute("SELECT * FROM budgets ORDER BY name ASC")
    budgets = cursor.fetchall()
    budget_rows = []
    for budget in budgets:
        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS spent
            FROM transactions
            WHERE type='expense' AND category=? AND substr(date, 1, 7)=?
            """,
            (budget["name"], month_prefix),
        )
        spent = cursor.fetchone()["spent"]
        limit_amount = budget["monthly_limit"] or 0
        usage = round((spent / limit_amount) * 100, 1) if limit_amount > 0 else 0
        budget_rows.append(
            {
                "id": budget["id"],
                "name": budget["name"],
                "monthly_limit": limit_amount,
                "spent": spent,
                "remaining": limit_amount - spent,
                "usage": usage,
                "status": "Over budget" if usage > 100 else "On track" if usage < 85 else "Watch closely",
            }
        )
    cursor.execute("SELECT * FROM bills ORDER BY due_date ASC")
    bills = cursor.fetchall()
    bills_due_soon = []
    for bill in bills:
        due = parse_date(bill["due_date"])
        days_until = (due - today).days if due else None
        bills_due_soon.append({**dict(bill), "days_until": days_until})
    cursor.execute("SELECT * FROM goals ORDER BY name ASC")
    goals = []
    for goal in cursor.fetchall():
        progress = round((goal["current_amount"] / goal["target_amount"]) * 100, 1) if goal["target_amount"] > 0 else 0
        goals.append({**dict(goal), "progress": progress})
    cursor.execute("SELECT * FROM investments ORDER BY name ASC")
    investments = []
    for investment in cursor.fetchall():
        change = investment["current_value"] - investment["cost_basis"]
        change_pct = round((change / investment["cost_basis"]) * 100, 1) if investment["cost_basis"] > 0 else 0
        investments.append({**dict(investment), "change": change, "change_pct": change_pct})
    cursor.execute(
        """
        SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE type='expense' AND substr(date, 1, 7)=?
        GROUP BY category
        ORDER BY total DESC
        LIMIT 5
        """,
        (month_prefix,),
    )
    spending_summary = [dict(row) for row in cursor.fetchall()]
    monthly_budget_total = sum(item["monthly_limit"] for item in budget_rows)
    monthly_budget_used = sum(item["spent"] for item in budget_rows)
    net_worth = savings + sum(item["current_value"] for item in investments)
    cash_reserve = max(savings, 0)
    alerts = []
    recommendations = []
    if total_income > 0 and total_expense >= total_income * 0.9:
        alerts.append("Your expenses have reached at least 90% of total income.")
        recommendations.append("Trim discretionary spending this month to protect your savings rate.")
    overspent = [item for item in budget_rows if item["usage"] > 100]
    if overspent:
        alerts.append(f"{overspent[0]['name']} is over budget this month.")
        recommendations.append(f"Review {overspent[0]['name']} transactions and reduce repeat spending there first.")
    upcoming_bills = [bill for bill in bills_due_soon if bill["status"] != "paid" and bill["days_until"] is not None and bill["days_until"] <= 7]
    if upcoming_bills:
        alerts.append(f"{upcoming_bills[0]['title']} is due in {upcoming_bills[0]['days_until']} day(s).")
        recommendations.append("Set aside cash now for upcoming bills to avoid disrupting your weekly budget.")
    slow_goals = [goal for goal in goals if goal["progress"] < 50]
    if slow_goals:
        recommendations.append(f"Your {slow_goals[0]['name']} goal is below 50% complete, so a small recurring transfer could help.")
    profitable_investments = [item for item in investments if item["change"] > 0]
    if profitable_investments:
        recommendations.append(f"{profitable_investments[0]['name']} is up {profitable_investments[0]['change_pct']}% from cost basis.")
    if not recommendations:
        recommendations.append("Your finances look balanced right now. Keep logging transactions to maintain accurate insights.")
    return {
        "today": today.isoformat(),
        "current_month_label": today.strftime("%B %Y"),
        "transactions": transactions,
        "total_income": total_income,
        "total_expense": total_expense,
        "savings": savings,
        "monthly_data": monthly_data,
        "monthly_savings": monthly_savings,
        "budgets": budget_rows,
        "bills": bills_due_soon,
        "goals": goals,
        "investments": investments,
        "spending_summary": spending_summary,
        "alerts": alerts,
        "recommendations": recommendations,
        "net_worth": net_worth,
        "cash_reserve": cash_reserve,
        "monthly_budget_total": monthly_budget_total,
        "monthly_budget_used": monthly_budget_used,
        "upcoming_bills_count": len(upcoming_bills),
        "navigation": get_navigation(),
    }
@app.context_processor
def inject_navigation():
    return {"navigation": get_navigation()}
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
    context = get_finance_context()
    return render_template("dashboard.html", active_page="dashboard", **context)
@app.route("/budgets")
@login_required
def budgets():
    context = get_finance_context()
    return render_template("budgets.html", active_page="budgets", **context)
@app.route("/bills")
@login_required
def bills():
    context = get_finance_context()
    return render_template("bills.html", active_page="bills", **context)
@app.route("/goals")
@login_required
def goals():
    context = get_finance_context()
    return render_template("goals.html", active_page="goals", **context)
@app.route("/investments")
@login_required
def investments():
    context = get_finance_context()
    return render_template("investments.html", active_page="investments", **context)
@app.route("/add-transaction", methods=["POST"])
@login_required
def add_transaction():
    transaction_date = request.form.get("date", "")
    description = request.form.get("description", "").strip()
    amount = parse_amount(request.form.get("amount"))
    type_ = request.form.get("type", "expense")
    selected_category = request.form.get("category", "Other")
    category = infer_category(description, type_, selected_category)
    cursor.execute(
        """
        INSERT INTO transactions (date, description, category, amount, type)
        VALUES (?, ?, ?, ?, ?)
        """,
        (transaction_date, description, category, amount, type_),
    )
    db.commit()
    return redirect(url_for("dashboard"))
@app.route("/add-budget", methods=["POST"])
@login_required
def add_budget():
    cursor.execute(
        "INSERT INTO budgets (name, monthly_limit) VALUES (?, ?)",
        (request.form.get("name", "").strip(), parse_amount(request.form.get("monthly_limit"))),
    )
    db.commit()
    return redirect(url_for("budgets"))
@app.route("/add-bill", methods=["POST"])
@login_required
def add_bill():
    cursor.execute(
        "INSERT INTO bills (title, amount, due_date, status) VALUES (?, ?, ?, ?)",
        (
            request.form.get("title", "").strip(),
            parse_amount(request.form.get("amount")),
            request.form.get("due_date", ""),
            request.form.get("status", "upcoming"),
        ),
    )
    db.commit()
    return redirect(url_for("bills"))
@app.route("/add-goal", methods=["POST"])
@login_required
def add_goal():
    cursor.execute(
        "INSERT INTO goals (name, target_amount, current_amount) VALUES (?, ?, ?)",
        (
            request.form.get("name", "").strip(),
            parse_amount(request.form.get("target_amount")),
            parse_amount(request.form.get("current_amount")),
        ),
    )
    db.commit()
    return redirect(url_for("goals"))
@app.route("/add-investment", methods=["POST"])
@login_required
def add_investment():
    cursor.execute(
        """
        INSERT INTO investments (name, asset_type, current_value, cost_basis)
        VALUES (?, ?, ?, ?)
        """,
        (
            request.form.get("name", "").strip(),
            request.form.get("asset_type", "").strip(),
            parse_amount(request.form.get("current_value")),
            parse_amount(request.form.get("cost_basis")),
        ),
    )
    db.commit()
    return redirect(url_for("investments"))
@app.route("/delete/<string:entity>/<int:item_id>")
@login_required
def delete_item(entity, item_id):
    tables = {
        "transaction": "transactions",
        "budget": "budgets",
        "bill": "bills",
        "goal": "goals",
        "investment": "investments",
    }
    redirects = {
        "transaction": "dashboard",
        "budget": "budgets",
        "bill": "bills",
        "goal": "goals",
        "investment": "investments",
    }
    table_name = tables.get(entity)
    if table_name:
        cursor.execute(f"DELETE FROM {table_name} WHERE id=?", (item_id,))
        db.commit()
        return redirect(url_for(redirects[entity]))
    return redirect(url_for("dashboard"))
if __name__ == "__main__":
    load_credentials()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
