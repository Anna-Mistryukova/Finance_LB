import os
import re
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    rows = db.execute("""
        SELECT symbol, name, SUM(shares) as total_shares
        FROM transactions
        WHERE user_id = :user_id
        GROUP BY symbol
        HAVING total_shares > 0
    """, user_id=session["user_id"])

    portfolio_value = 0
    cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]

    for row in rows:
        symbol = row["symbol"]
        shares = row["total_shares"]
        quote = lookup(symbol)
        total_value = shares * quote["price"]
        portfolio_value += total_value
        row["name"] = quote["name"]
        row["current_price"] = usd(quote["price"])
        row["total_value"] = usd(total_value)

    total_balance = portfolio_value + cash

    return render_template("index.html", rows=rows, cash=usd(cash), portfolio_value=usd(portfolio_value), total_balance=usd(total_balance))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))
        quote = lookup(symbol)

        if not symbol:
            return apology("Не указано название акции", 336)

        if not shares or shares <= 0:
            return apology("Не указано корректное количество акций", 336)

        if not quote:
            return apology("Акция не найдена", 336)

        user_id = session["user_id"]
        user_cash = db.execute("SELECT cash FROM users WHERE id = :id", id=user_id)[0]["cash"]

        total_price = quote["price"] * shares

        if user_cash < total_price:
            return apology("Недостаточно средств", 336)

        transected_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # Обновляем баланс пользователя
        db.execute("UPDATE users SET cash = cash - :total_price WHERE id = :id", total_price=total_price, id=user_id)

        # Записываем транзакцию
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, transected_at) VALUES (:user_id, :symbol, :shares, :price, :transected_at)",
                   user_id=user_id,  symbol=symbol, shares=shares, price=quote["price"], transected_at=transected_at)

        flash("Купленно!")

        return redirect("/")

    else:
        return render_template("buy.html")




@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    transactions = db.execute(""" SELECT symbol, price, transected_at, shares FROM transactions WHERE user_id = :user_id ORDER BY type DESC """, user_id=session["user_id"])

    return render_template("history.html", transactions=transactions, usd=usd)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Вход"""

    # Забыть любое user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Имя пользователя не было указано
        if not request.form.get("username"):
            return apology("Вы должны указать имя пользователя", 336)

        # Убедитесь, что пароль был отправлен
        elif not request.form.get("password"):
            return apology("Вы не ввели пароль", 336)

        # Запросить базу данных по имени пользователя
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # Убедитесь, что пользовтель существует и пароль верен
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("Извините, неправильное имя пользователя или пароль", 336)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # Пользователь достиг маршрута через GET (например, нажав ссылку или перенаправив)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Должен быть указан символ", 336)

        quote = lookup(symbol)
        if not quote:
            return apology("Не найдено", 336)

        return render_template("quoted.html", symbol=quote["symbol"], price=usd(quote["price"]))

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Регистрация пользователя"""
    # Забыть user_id
    session.clear()

    if request.method == "POST":

        if not request.form.get("username"):
            return apology("Необходимо указать имя пользователя", 336)

        elif not request.form.get("password"):
            return apology("must provide password", 336)

        elif not request.form.get("confirmation"):
            return apology("must provide password confirmation", 336)

        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 336)

        rows = db.execute("SELECT * FROM users WHERE username = :username", username = request.form.get("username"))

        # Проверка на минимальное количество букв, цифр и символов в пароле
        password = request.form.get("password")
        if not (re.search(r'[a-zA-Z]', password) and re.search(r'\d', password) and re.search(r'[!@#$%^&*(),.?":{}|<>]', password) and len(password) >= 5):
            return apology("Пароль должен содержать минимум 5 символов, включая буквы, цифры и символы", 336)

        if len(rows) != 0:
            return apology("Пользователь с таким именем уже есть в системе", 336)

        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)",
                   request.form.get("username"),
                   generate_password_hash(request.form.get("password")))

        return redirect("/")
    # Пользователь достиг маршрута через GET (например, нажав ссылку или перенаправив)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))
        quote = lookup(symbol)

        if not symbol:
            return apology("Не выбрана акция для продажи", 336)

        if not shares or shares <= 0:
            return apology("Указано некорректное количество акций для продажи", 336)

        user_id = session["user_id"]

        # Получить количество акций пользователя для выбранного символа
        user_shares = db.execute("SELECT SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id AND symbol = :symbol",
                                 user_id=user_id, symbol=symbol)[0]["total_shares"]

        if not user_shares or user_shares < shares:
            return apology("У вас недостаточно акций для продажи", 336)

        total_price = quote["price"] * shares
        transected_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Обновить баланс пользователя
        db.execute("UPDATE users SET cash = cash + :total_price WHERE id = :user_id", total_price=total_price, user_id=user_id)

        # Записать транзакцию продажи
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, transected_at) VALUES (:user_id, :symbol, :shares, :price, :transected_at)",
                   user_id=user_id, symbol=symbol, shares=(-1) * shares, price=quote["price"], transected_at=transected_at)

        flash("Продано!")

        return redirect("/")

    else:
        # Получите список акций, которые пользователь владеет
        user_stocks = db.execute("""
            SELECT symbol
            FROM transactions
            WHERE user_id = :user_id
            GROUP BY symbol
            HAVING SUM(shares) > 0
        """, user_id=session["user_id"])

        return render_template("sell.html", user_stocks=user_stocks)
