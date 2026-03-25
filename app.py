from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
from authlib.integrations.flask_client import OAuth
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# ------------------------
# CONFIG
# ------------------------

import os
from dotenv import load_dotenv

load_dotenv()  # loads .env file

app = Flask(__name__)

# ------------------------
# CONFIG
# ------------------------

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "fallback-secret")

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expenses.db'

# GOOGLE CONFIG (SAFE)
app.config['GOOGLE_CLIENT_ID'] = os.getenv("GOOGLE_CLIENT_ID")
app.config['GOOGLE_CLIENT_SECRET'] = os.getenv("GOOGLE_CLIENT_SECRET")

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ------------------------
# GOOGLE OAUTH
# ------------------------

oauth = OAuth(app)

google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# ------------------------
# MODELS
# ------------------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))
    google_id = db.Column(db.String(200), unique=True)   # ✅ FIXED


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float)
    category = db.Column(db.String(100))
    date = db.Column(db.String(100))
    user_id = db.Column(db.Integer)


# ------------------------
# LOGIN MANAGER
# ------------------------

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ------------------------
# ROUTES
# ------------------------

@app.route('/')
@login_required
def home():
    return render_template('index.html')


# -------- LOGIN --------
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if not user:
            error = "❌ User not found"
        elif not check_password_hash(user.password, password):
            error = "❌ Wrong password"
        else:
            login_user(user)
            return redirect('/')

    return render_template('login.html', error=error)


# -------- GOOGLE LOGIN --------
@app.route('/login/google')
def login_google():
    return google.authorize_redirect(url_for('authorize', _external=True))


# -------- GOOGLE CALLBACK --------
@app.route('/authorize')
def authorize():
    token = google.authorize_access_token()

    # ✅ Correct FULL URL
    user_info = google.get('https://www.googleapis.com/oauth2/v2/userinfo').json()

    email = user_info['email']
    name = user_info.get('name')

    user = User.query.filter_by(username=email).first()

    if not user:
        user = User(username=email, password="")
        db.session.add(user)
        db.session.commit()

    login_user(user)
    return redirect('/')


# -------- REGISTER --------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hashed_password = generate_password_hash(request.form['password'])

        new_user = User(
            username=request.form['username'],
            password=hashed_password
        )

        db.session.add(new_user)
        db.session.commit()

        return redirect('/login')

    return render_template('register.html')


# -------- LOGOUT --------
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')


# -------- ADD EXPENSE --------
@app.route('/add', methods=['POST'])
@login_required
def add_expense():
    data = request.json

    expense = Expense(
        amount=float(data['amount']),
        category=data['category'],
        date=datetime.now().strftime("%Y-%m-%d"),
        user_id=current_user.id
    )

    db.session.add(expense)
    db.session.commit()

    return jsonify({"status": "success"})


# -------- GET DATA --------
@app.route('/data')
@login_required
def get_data():
    expenses = Expense.query.filter_by(user_id=current_user.id).all()

    category_data = {}
    daily_data = {}
    total = 0

    for e in expenses:
        total += e.amount
        category_data[e.category] = category_data.get(e.category, 0) + e.amount
        daily_data[e.date] = daily_data.get(e.date, 0) + e.amount

    return jsonify({
        "category": category_data,
        "daily": daily_data,
        "total": total
    })

from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_input = data.get("message")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an AI expense assistant. Analyze spending and give helpful insights."},
                {"role": "user", "content": user_input}
            ]
        )

        reply = response.choices[0].message.content
        return {"reply": reply}

    except Exception as e:
        return {"reply": str(e)}


# ------------------------
# RUN
# ------------------------

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True)