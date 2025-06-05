from flask import request, jsonify, Blueprint
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from psycopg2 import connect
import random
from datetime import datetime, timezone
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

# Changed route to prevent conflict with route above #TODO: CHECK WHAT THIS CHANGE MEANS
@user_api.route('/lots/<string:lot_id>/availability', methods=['GET'])
def get_free_spots(lot_id):
    """
    Returns the number of available parking spots for a given lot.
    Data is read from the Redis hash 'parking_lot:<lot_id>', using
    'car_num' (current occupied spots) and 'parking_spot_num' (total spots).
    """
    lot_key = f"parking_lot:{lot_id}"
    if not redis_client.exists(lot_key):
        return jsonify({"message": f"Lot {lot_id} not found"}), 404

    lot_info = redis_client.hmget(lot_key, "car_num", "parking_spot_num")
    car_num_str = lot_info[0]
    parking_spot_num_str = lot_info[1]

    if car_num_str is None or parking_spot_num_str is None:
        return jsonify({"message": f"Lot {lot_id} data is incomplete in Redis (missing car_num or parking_spot_num)."}), 500

    try:
        car_num = int(car_num_str)
        parking_spot_num = int(parking_spot_num_str)
    except ValueError:
        return jsonify({"message": f"Invalid data types for car_num or parking_spot_num in Redis for lot {lot_id}."}), 500

    available_spots = parking_spot_num - car_num
    # Ensure available_spots is not negative if data is somehow inconsistent
    available_spots = max(0, available_spots)

    return jsonify({"lot_id": lot_id, "available_spots": available_spots}), 200

@user_api.route('/reserve', methods = ['POST'])
def reserve():
    data = request.get_json()
    reservation_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    #Check if the lot exists in MongoDB
    lot_id = data["id_parking_lot"]
    if not parks_collection.find_one({"_id": ObjectId(lot_id)}):
        return jsonify({"message": "No such parking lot found."}), 404
    
    # id_parking_spot is no longer used to check Redis state for an individual spot,
    # but it might be kept for other logging or future use if individual spot management is re-introduced.
    # For now, we check aggregate availability.
    # spot_id = data.get("id_parking_spot") # TODO: Keep if client sends it and it's used elsewhere

    lot_key = f"parking_lot:{lot_id}"
    if not redis_client.exists(lot_key):
        return jsonify({"message": "Lot not found or not yet initialized"}), 404

    # Check aggregate availability
    lot_info = redis_client.hmget(lot_key, "car_num", "parking_spot_num")
    car_num_str = lot_info[0]
    parking_spot_num_str = lot_info[1]

    if car_num_str is None or parking_spot_num_str is None:
        return jsonify({"message": f"Lot {lot_id} data is incomplete in Redis."}), 500

    try:
        car_num = int(car_num_str)
        parking_spot_num = int(parking_spot_num_str)
    except ValueError:
        return jsonify({"message": f"Invalid numeric data in Redis for lot {lot_id}."}), 500

    if car_num >= parking_spot_num:
        return jsonify({"message": "Parking lot is full"}), 400

    # Proceed with TimescaleDB reservation
    try:
        timescale_cursor.execute(
            """
            INSERT INTO parking_transactions
                (parking_lot_id, parking_spot_id, user_id, entry_timestamp, exit_timestamp, checkout_price)
            VALUES (%s, %s, %s, NOW(), %s, %s)
            """
        # Assuming parking_spot_id in transaction can be null or a placeholder if not reserving a specific one
        , (lot_id, None, data['id_user'], None, None)) #data.get("id_parking_spot") on index 1 if we decide to use analytics on it
        timescale_conn.commit()
    
    except Exception as e:
        timescale_conn.rollback()
        return jsonify({"message": f"Database error, reservation canceled: {str(e)}"}), 500
    
    # Increment car_num in Redis and update timestamp - TODO: THIS IS DONE WITH CV model, reserving does not increment counter. POTENTIALLY IT CAN FORCE THE MODEL TO RECALC NUMBER OF CARS
    # Use a pipeline for atomicity of Redis updates if preferred, though HINCRBY is atomic itself.
    #new_car_num = redis_client.hincrby(lot_key, "car_num", 1)
    #redis_client.hset(lot_key, "update_timestamp", datetime.utcnow().isoformat())
    #print(f"Lot {lot_id} car_num incremented to {new_car_num} after reservation.")

    return jsonify({
        "message": "Reservation successful", 
        "code": reservation_code
    }), 200
    
@user_api.route('/checkout', methods = ['POST'])
def checkout():
    """
    POST body should contain:
      {
        "id_parking_lot": "<Mongo ObjectID as string>",
        "id_parking_spot": "<Mongo ObjectID as string>",
        "id_user": "<User ID from Mongo>" // This is used to find the transaction
      }
    """

    data = request.get_json()
    
    # 1) Validate input
    lot_id = data.get('id_parking_lot')
    spot_id = data.get('id_parking_spot')
    user_id = data.get('id_user')
    if not (lot_id and spot_id and user_id):
        return jsonify({"message": "Missing one of required fields: id_parking_lot, id_parking_spot, id_user"}), 400

    lot_key = f"parking_lot:{lot_id}" # Define lot_key early

    # 2) Check the TimescaleDB table for an active reservation
    timescale_cursor.execute("""
        SELECT parking_lot_id, parking_spot_id, user_id, entry_timestamp, exit_timestamp
        FROM parking_transactions
        WHERE parking_lot_id = %s
          AND user_id = %s
          AND exit_timestamp IS NULL 
        LIMIT 1
    """, (lot_id, user_id))
    reservation = timescale_cursor.fetchone()

    if not reservation:
        return jsonify({"message": "No active reservation found for this user, spot, and lot"}), 404

    entry_time = reservation['entry_timestamp']
    entry_time = entry_time.replace(tzinfo = timezone.utc)
    # Make sure we have an entry_time
    if not entry_time:
        return jsonify({"message": "The reservation has no entry_timestamp"}), 500

    # 3) Calculate how long they've stayed
    leave_time = datetime.now().replace(tzinfo = timezone.utc)
    duration_hours = (leave_time - entry_time).total_seconds() / 3600
    duration_hours = max(1, int(duration_hours))  # Minimum 1 hour

    # 4) Retrieve the parking lot doc from Mongo to get the price_per_hour
    parking_lot_doc = parks_collection.find_one({"_id": ObjectId(lot_id)})
    if not parking_lot_doc:
        return jsonify({"message": "Parking lot not found in DB (strange)"}), 404

    price_per_hour = parking_lot_doc.get("price_per_hour", 2.0)  # fallback if missing

    total_cost = round(duration_hours * price_per_hour, 2)

    # 5) Update the TimescaleDB record: exit_timestamp + cost
    try:
        timescale_cursor.execute("""
            UPDATE parking_transactions
            SET exit_timestamp = NOW(),
                checkout_price = %s
            WHERE parking_lot_id = %s
              AND user_id = %s
              AND exit_timestamp IS NULL
        """, (total_cost, lot_id, user_id))
        timescale_conn.commit()
    except Exception as e:
        timescale_conn.rollback()
        return jsonify({"message": f"Database error during checkout: {str(e)}"}), 500

    # 6) Decrement car_num in Redis and update timestamp
    #new_car_num = redis_client.hincrby(lot_key, "car_num", -1) #TODO: SAME COMMENT AS FOR reserve()
    # Ensure car_num doesn't go below zero due to potential race conditions or errors elsewhere
    # Though HINCRBY itself won't make it negative unless it was already negative.
    #redis_client.hset(lot_key, "update_timestamp", datetime.utcnow().isoformat())
    #print(f"Lot {lot_id} car_num decremented to {new_car_num} after checkout.")

    # 7) Return success
    return jsonify({
        "message": "Checkout successful",
        "duration_hours": duration_hours,
        "total_cost": total_cost
    }), 200

#----------------------------------------------------------------------------------------------------
#   Route Configuration
#----------------------------------------------------------------------------------------------------

def configure_routes(app):
    app.register_blueprint(user_api, url_prefix = '/user')