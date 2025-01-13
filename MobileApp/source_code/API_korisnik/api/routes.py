from flask import request, jsonify, Blueprint
from pymongo import MongoClient
import os
from dotenv import load_dotenv
import random
from datetime import datetime
from app import timescale_conn

user_api = Blueprint('user_api', __name__)

#----------------------------------------------------------------------------------------------------
#   Setting Up MongoDB and TimescaleDB
#----------------------------------------------------------------------------------------------------

#Loading the environment variables
load_dotenv()

#MongoDB Configuration
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://user_Person:mongo_pass@mongo_user_db_service:27017/ParkMan_user_db")
client = MongoClient(MONGO_URI)
db = client.get_database()

#MongoDB Collections
users_collection = db.users
parks_collection = db.parks

#TimescaleDB Configuration
timescale_cursor = timescale_conn.cursor()

#----------------------------------------------------------------------------------------------------
#   User Registration and Login
#----------------------------------------------------------------------------------------------------

@user_api.route('/register', methods = ['POST'])
def register():
    data = request.get_json()
    if not data.get('name') or not data.get('surname'):
        return jsonify({"message": "Missing required fields: name or surname"}), 400
    
    user = {
        "name": data['name'],
        "surname": data['surname'],
        "car_registration": data.get('car_registration', []) #Empty list for storing users car registration numbers
    }

    result = users_collection.insert_one(user)
    return jsonify({"message": "User registered successfully", "id": str(result.inserted_id)}), 201

@user_api.route('/login', methods = ['POST'])
def login():
    data = request.get_json()
    if not data.get('name') or not data.get('surname'):
        return jsonify({"message": "Missing required fields: name or surname"}), 400
    
    #Query user in MongoDB
    user = users_collection.find_one({"name": data['name'], "surname": data['surname']})
    if user:
        return jsonify({"message": "Login successful", "user": user})
    else:
        return jsonify({"message": "Invalid username or password"})

#----------------------------------------------------------------------------------------------------
#   Getting all the parks, reserving a park and park checkout
#----------------------------------------------------------------------------------------------------
    
@user_api.route('/parks', methods = ['GET'])
def get_parks():
    parks = list(parks_collection.find({}, {"_id": 0})) #{"_id: 0"} - Exclude the ID of the owner when outputing results
    return jsonify(parks)

@user_api.route('/reserve', methods = ['POST'])
def reserve():
    data = request.get_json()
    reservation_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])

    park = parks_collection.find_one({"id": data['park_id'], "available_spots": {"$gt": 0}})
    if park:
        #Update the available spots in the park
        parks_collection.update_one({"id": data['park_id']}, {"$inc": {"available_spots": -1}})
        #Insert reservation into TimescaleDB
        timescale_cursor.execute("""
            INSERT INTO TimestampDB (id_parking_lot, id_user, timestamp, id_parking_spot)
            VALUES (%s, %s, NOW(), %s)
        """, (data['park_id'], data['user_id'], data.get('id_parking_spot'))
        )
        timescale_conn.commit()
        return jsonify({"message": "Reservation successful", "code": reservation_code})
    else:
        return jsonify({"message": "Reservation failed, no spots available"})
    
@user_api.route('/checkout', methods = ['POST'])
def checkout():
    data = request.get_json()

    #Retrieve the resertvation from TimescaleDB
    timescale_cursor.execute("""
        SELECT * FROM TimestampDB
        WHERE id_parking_lot = %s AND id_user = %s AND leaving_timestamp IS NULL
    """, (data['park_id'], data['user_id'])
    )
    reservation = timescale_cursor.fetchone()

    if not reservation:
        return jsonify({"message": "Reservation not found"}), 404
    
    #Calculate visit duration and cost
    entry_time = reservation['timestamp']
    leave_time = datetime.utcnow()
    duration_hours = (leave_time - entry_time).total_seconds() / 3600
    duration_hours = max(1, int(duration_hours)) #Minimum payment is one hour

    #Retrieve parking lot price
    parking_lot = parks_collection.find_one({"id": data['park_id']})
    price_per_hour = parking_lot.get("price_per_hour", 2.0) #Default price if not set differently

    total_cost = round(duration_hours * price_per_hour, 2)

    #Updating TimestampDB record with leaving timestamp and cost
    timescale_cursor.execute("""
        UPDATE TimestampDB
        SET leaving_timestamp = NOW(), checkout_price = %s
        WHERE id_parking_lot = %s AND id_user = %s id_parking_spot = %s
    """, (total_cost, data['park_id'], data['user_id'], reservation['id_parking_spot'])
    )
    timescale_conn.commit()

    #Increment available spots in MongoDB
    parks_collection.update_one({"id": data['park_id']}, {"$inc": {"available_spots": 1}})

    return jsonify({
        "message": "Checkout successful",
        "duration_hours": duration_hours,
        "total_cost": total_cost
    })

#----------------------------------------------------------------------------------------------------
#   Route Configuration
#----------------------------------------------------------------------------------------------------

def configure_routes(app):
    app.register_blueprint(user_api, url_prefix = '/user')