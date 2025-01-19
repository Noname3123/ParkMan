from flask import request, jsonify, Blueprint
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from psycopg2 import connect
import random
from datetime import datetime
from bson import ObjectId
#from app import timescale_conn #from app import timescale_conn causes circular import issues

user_api = Blueprint('user_api', __name__)

#----------------------------------------------------------------------------------------------------
#   Setting Up MongoDB and TimescaleDB
#----------------------------------------------------------------------------------------------------

#Loading the environment variables
load_dotenv()

#MongoDB Configuration
MONGO_URI = os.getenv("MONGO_USER_DATABASE_URI", "mongodb://user_Person:mongo_pass@mongo_user_db_service:27017/ParkMan_user_db")
client = MongoClient(MONGO_URI)
db = client.get_database()

MONGO_EXTERNAL=os.getenv("MONGO_MANAGER_DATABASE_R_ONLY_URI", "mongodb://external:external_pass@localhost:27017/ParkMan_manager_db")
external_client=MongoClient(MONGO_EXTERNAL)
db_external=external_client.get_database()


#MongoDB Collections
users_collection = db.users
parks_collection = db_external.parking_lots #parking lot collection

#TimescaleDB Configuration
TIMESCALE_DB_URI = os.getenv("TIMESCALE_DB_DATABASE_URI", "postgresql://postgres_user:postgres_pass@localhost:5432/ParkingTransactionsDB")

timescale_conn = connect(TIMESCALE_DB_URI)
timescale_cursor = timescale_conn.cursor(cursor_factory = RealDictCursor)

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
        "car_registration": data.get('car_registration', []), #Empty list for storing users car registration numbers
        "home_geolocation": data.get('home_geolocation'),
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
def get_parks(): #TODO: this should be used as get closest park to user's location
    parks = list(parks_collection.find({}, {"_id": 0})) #{"_id: 0"} - Exclude the ID of the owner when outputing results
    return jsonify(parks)

@user_api.route('/reserve', methods = ['POST'])
def reserve():
    data = request.get_json()
    reservation_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    #park = parks_collection.find_one({"id": data['park_id'], "available_spots": {"$gt": 0}}) #TODO: available spots are not part of MongoDB (Key-valueDB)
    #TODO: add check whether parking lot (data["id_parking_lot"]) is free and exists in MongoDB - phase 2
    if True and parks_collection.find_one({"_id": ObjectId(data["id_parking_lot"])}):
        #Update the available spots in the park
        #parks_collection.update_one({"id": data['park_id']}, {"$inc": {"available_spots": -1}}) - ##TODO: KeyValueDB - sensors do this
        #Insert reservation into TimescaleDB
        timescale_cursor.execute("""
            INSERT INTO parking_transactions(parking_lot_id, parking_spot_id, user_id, entry_timestamp, exit_timestamp, checkout_price )
            VALUES (%s, %s, %s, NOW(), %s, %s)
        """, (data['id_parking_lot'],data.get('id_parking_spot') ,data['id_user'], None, None)
        )
        timescale_conn.commit()
        return jsonify({"message": "Reservation successful", "code": reservation_code})#TODO: make the id of transaction as reservation_code #TODO: look how to use this - it will probably get sent to mobile app storage of user
    else:
        return jsonify({"message": "Reservation failed, no spots available"})
    
@user_api.route('/checkout', methods = ['POST'])
def checkout():
    data = request.get_json()

    #Retrieve the resertvation from TimescaleDB
    timescale_cursor.execute("""
        SELECT * FROM parking_transactions
        WHERE parking_lot_id = %s AND user_id = %s AND exit_timestamp IS NULL
    """, (data['id_parking_lot'], data['id_user'])
    )
    reservation = timescale_cursor.fetchone()

    if not reservation:
        return jsonify({"message": "Reservation not found"}), 404
    
    #Calculate visit duration and cost
    entry_time = reservation['timestamp']
    leave_time = datetime.utcnow() #TODO: update since deprecated
    duration_hours = (leave_time - entry_time).total_seconds() / 3600
    duration_hours = max(1, int(duration_hours)) #Minimum payment is one hour

    #Retrieve parking lot price
    parking_lot = parks_collection.find_one({"id": data['park_id']})
    price_per_hour = parking_lot.get("price_per_hour", 2.0) #Default price if not set differently

    total_cost = round(duration_hours * price_per_hour, 2)

    #Updating TimestampDB record with leaving timestamp and cost
    timescale_cursor.execute("""
        UPDATE parking_transactions
        SET exit_timestamp = NOW(), checkout_price = %s
        WHERE parking_lot_id = %s AND user_id = %s parking_spot_id = %s
    """, (total_cost, data['id_parking_lot'], data['id_user'], reservation['id_parking_spot'])
    )
    timescale_conn.commit()

    #TODO: Increment available spots in MongoDB - this is related to key-val DB - phase 2
    ##parks_collection.update_one({"id": data['id_parking_lot']}, {"$inc": {"available_spots": 1}})

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