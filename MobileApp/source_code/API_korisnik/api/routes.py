from flask import request, jsonify, Blueprint
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from psycopg2 import connect
import random
from datetime import datetime
from bson import ObjectId
import redis

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
#   Setting Up Redis
#----------------------------------------------------------------------------------------------------

REDIS_HOST = os.getenv("REDIS_HOST", "redis_parking_spots_status")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.StrictRedis(host = REDIS_HOST, port = REDIS_PORT, decode_responses = True)

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
#   Getting the closest park, free spots, reserving a park and park checkout
#----------------------------------------------------------------------------------------------------
    
@user_api.route('/parks', methods = ['GET'])
def get_parks(): #TODO: this should be used as get closest park to user's location
    parks = list(parks_collection.find({}, {"_id": 0})) #{"_id: 0"} - Exclude the ID of the owner when outputing results
    return jsonify(parks)

@user_api.route('/parks', methods = ['GET'])
def get_free_spots(lot_id):
    """
    Returns a list of free (unoccupied) spot IDs for a given lot, 
    based on the Redis hash: parking_lot:<lot_id>.
    Fields in that hash look like:
       spot_<spotId> => "false" or "true"
    """
    lot_key = f"parking_lot:{lot_id}"
    if not redis_client.exists(lot_key):
        return jsonify({"message": f"Lot {lot_id} not found"}), 404
    
    #Get data about spots
    spot_data = redis_client.hgetall(lot_key)

    #Now isolate free spots
    free_spots = []
    for field, value in spot_data.items():
        if field.startswith("spot_") and not field.endswith("_last_update"):
            if value == "false":
                _, spot_id_str = field.split("_", 1)
                free_spots.append(spot_id_str)

    return jsonify({"lot_id": lot_id, "free_spots": free_spots}), 200

@user_api.route('/reserve', methods = ['POST'])
def reserve():
    data = request.get_json()
    reservation_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    #Check if the lot exists in MongoDB
    lot_id = data["id_parking_lot"]
    if not parks_collection.find_one({"_id": ObjectId(lot_id)}):
        return jsonify({"message": "No such parking lot found."}), 404
    
    #If the spot is found, confirm it's not occupied
    spot_id = data.get("id_parking_spot")
    if not spot_id:
        return jsonify({"message": "Missing required field: id_parking_spot"}), 400
    
    lot_key = f"parking_lot:{lot_id}"
    spot_field = f"spot_{spot_id}"

    #If the lot or the spot is not found
    if not redis_client.exists(lot_key):
        return jsonify({"message": "Lot not found or not yet initialized"}), 404
    
    #Check the occupation
    spot_status = redis_client.hget(lot_key, spot_field)
    if spot_status in None:
        return jsonify({"message": "Spot not found"}), 404
    
    if spot_status == "true":
        return jsonify({"message": "Spot is currently occupied"}), 400
    
    #Now we know the spot is free, so from now on mark it as "true" which means it is occupied
    #The spot will be marked as occupied (reserved) only if the TimescaleDB reservation has successfully been commited
    #We will roll back the transaction if the Redis insert fails
    try:
        timescale_cursor.execute(
            """
            INSERT INTO parking_transactions
                (parking_lot_id, parking_spot_id, user_id, entry_timestamp, exit_timestamp, checkout_price)
            VALUES (%s, %s, %s, NOW(), %s, %s)
            """
        , (lot_id, spot_id, data['id_user'], None, None))
        timescale_conn.commit()
    
    except Exception as e:
        timescale_conn.rollback()
        return jsonify({"message": f"Database error, reservation canceled: {str(e)}"}), 500
    
    redis_client.hset(lot_key, spot_field, "true")

    return jsonify({
        "message": "Reservation successful", 
        "code": reservation_code
    }), 200
    
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