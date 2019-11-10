"""Modules include sql ORM, time formatting, http requests, and secret key storage."""
from datetime import datetime, timedelta
import os
import jwt
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
import requests
from config.keys import keys

app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'db_temp.sqlite')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
ma = Marshmallow(app)

# TODO: Modularize code

# Models and Schemas Declaration
class User(db.Model):
    user_id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100))
    password = db.Column(db.String(100))
    token = db.Column(db.String)

    def __init__(self, email, password, token):
        self.email = email
        self.password = password
        self.token = token

class UserSchema(ma.Schema):
    class Meta:
        fields = ('user_id', 'email', 'password', 'token')

class Asset(db.Model):
    asset_id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(4))
    pl = db.Column(db.Float)
    num_owned = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('user.user_id'))
    user = db.relationship('User', backref='assets')

    def __init__(self, symbol, pl, num_owned, user_id):
        self.symbol = symbol
        self.pl = pl
        self.num_owned = num_owned
        self.user_id = user_id

class AssetSchema(ma.Schema):
    class Meta:
        fields = ('asset_id', 'symbol', 'pl', 'num_owned', 'user_id')

class FBTransaction(db.Model):
    trans_id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.Integer)
    amount = db.Column(db.Integer)
    trans_type = db.Column(db.String(4))
    price = db.Column(db.Float)
    user_id = db.Column(db.Integer, db.ForeignKey('user.user_id'))
    user = db.relationship('User', backref='fbtransactions')

    def __init__(self, timestamp, amount, trans_type, price, user_id):
        self.timestamp = timestamp
        self.amount = amount
        self.trans_type = trans_type
        self.price = price
        self.user_id = user_id

class FBTransactionSchema(ma.Schema):
    class Meta:
        fields = ('trans_id', 'timestamp', 'amount', 'trans_type', 'price', 'user_id')

user_schema = UserSchema()
users_schema = UserSchema(many=True)
asset_schema = AssetSchema()
assets_schema = AssetSchema(many=True)
transaction_FB_schema = FBTransactionSchema()
transactions_FB_schema = FBTransactionSchema(many=True)


# Routes Declaration
@app.route('/api/user/register', methods=['POST'])
def register_user():
    if (db.session.query(User.user_id).filter_by(email=request.json['email']).scalar() is not None):
        return jsonify(status=400, description='User already exists.')

    email = request.json['email']
    password = request.json['password']

    secret = keys['server_key']
    payload = {'email': email, 'password': password, 'login_time': str(datetime.now()), 'token_expire': str(datetime.now() + timedelta(hours=1))}
    encoded_jwt = jwt.encode(payload, secret, algorithm='HS256')

    new_user = User(email, password, encoded_jwt)

    db.session.add(new_user)
    db.session.commit()

    return user_schema.jsonify(new_user)

@app.route('/api/user/login', methods=['POST'])
def login_user():
    if (db.session.query(User.user_id).filter_by(email=request.json['email']).scalar() is None):
        return jsonify(status=400, description='User does not exist.')

    user_cred_check = User.query.filter_by(email=request.json['email']).first()

    if user_cred_check.password == request.json['password']:
        secret = keys['server_key']
        payload = {'email': user_cred_check.email, 'password': user_cred_check.password, 'login_time': str(datetime.now()), 'token_expire': str(datetime.now() + timedelta(hours=1))}
        encoded_jwt = jwt.encode(payload, secret, algorithm='HS256')

        user_cred_check.token = encoded_jwt

        db.session.commit()

        return user_schema.jsonify(user_cred_check)
    else:
        return jsonify(status=400, description='Incorrect password.')

@app.route('/api/user/verify', methods=['GET'])
def verify_user():
    token = request.headers.get('token')
    
    if token is None:
        return jsonify(status=400, description='Authentication token not sent.', authenticated=False)

    decoded = jwt.decode(token, keys['server_key'], algorithm='HS256')

    if datetime.strptime(decoded['token_expire'], "%Y-%m-%d %H:%M:%S.%f") < datetime.now():
        return jsonify(status=400, description='Authentication token has expired.', authenticated=False)

    return jsonify(status=200, description='User is authenticated.', authenticated=True)

@app.route('/api/quotes/FB', methods=['GET'])
def get_price():
    response = requests.get('https://sandbox.tradier.com/v1/markets/quotes',
                            params={'symbols': 'FB', 'greeks': 'false'},
                            headers={'Authorization': keys['fb_access_token'],
                                     'Accept': 'application/json'})
    fb_quote = response.json()['quotes']['quote']
    return jsonify(symbol=fb_quote['symbol'], description=fb_quote['description'], quote=fb_quote['last'])

@app.route('/api/transactions/FB', methods=['POST'])
def create_transaction():
    verify = requests.get('http://localhost:5000/api/user/verify', 
                          headers={'token': request.headers.get('token')}).json()

    if verify['authenticated'] == False:
        return jsonify(status=400, description='User not authenticated.')

    timestamp = datetime.now()
    trans_type = request.json['trans_type']
    amount = request.json['amount']
    price = requests.get('http://localhost:5000/api/quotes/FB').json()['quote']
    user_id = request.json['user_id']

    new_transaction = FBTransaction(timestamp, amount, trans_type, price, user_id)

    db.session.add(new_transaction)
    db.session.commit()

    return transaction_FB_schema.jsonify(new_transaction)

@app.route('/api/transactions/admin/FB', methods=['GET', 'POST'])
def get_FB_transactions():
    all_transactions = FBTransaction.query.all()
    result = transactions_FB_schema.dump(all_transactions)
    return jsonify(result)

if __name__ == "__main__":
    app.run('localhost', 5000, debug=True)