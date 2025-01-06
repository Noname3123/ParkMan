from flask import request, jsonify, Blueprint
import random

user_api = Blueprint('user_api', __name__)

users = []
parks = []

@user_api.route('/register', methods = ['POST'])
def register():
    data = request.get_json()
    print("Data is here!")
    users.append(data)
    return jsonify({"message": "User registered successfully"}), 201

@user_api.route('/login', methods = ['POST'])
def login():
    data = request.get_json()
    user = next((user for user in users if user['username'] == data['username'] and user['password'] == data['password']), None)
    if user is not None:
        return jsonify({"message": "Login successful"})
    else:
        return jsonify({"message": "Invalid username or password"}), 401
    
@user_api.route('/parks', methods = ['GET'])
def get_parks():
    return jsonify(parks)

@user_api.route('/reserve', methods = ['POST'])
def reserve():
    data = request.get_json()
    reservation_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])

    if "park_id" in data and any(park['id'] == data['park_id'] and park['available_spots'] > 0 for park in parks):
        return jsonify({"message": "Reservation successful", "code": reservation_code})
    else:
        return jsonify({"message": "Reservation failed, no spots available"}), 400
    
@user_api.route('/checkout', methods = ['POST'])
def checkout():
    #Potrebno doraditi kada bude baza povezana
    data = request.get_json()
    return jsonify({"message": "Checkout successful, thank you for your visit"})

def configure_routes(app):
    app.register_blueprint(user_api, url_prefix = '/user')