from flask import request, jsonify, Blueprint
import os
import redis
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime

sensor_api = Blueprint('sensor_api', __name__)

load_dotenv()

#-------------------------------------------------------------------
# MongoDB Configuration 
#-------------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_MANAGER_DATABASE_R_ONLY_URI", "mongodb://external:external_pass@localhost:27017/ParkMan_manager_db")
mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client.get_database()

users_collection = mongo_db.users
parking_lots_collection = mongo_db.parking_lots
parking_spots_collection = mongo_db.parking_spots

#-------------------------------------------------------------------
# Redis Configuration (Key-Value store for sensor data)
#-------------------------------------------------------------------
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.StrictRedis(host = REDIS_HOST, port = REDIS_PORT, decode_responses = True)

#-------------------------------------------------------------------
# Sensor API Endpoints
#-------------------------------------------------------------------

###############################################################################
# Updating a SINGLE SPOT within a specific LOT
###############################################################################
@sensor_api.route('/update_spot_status', methods=['POST'])
def update_spot_status():
    """
    Expects JSON payload:
    {
        "lot_id": "string",
        "car_num": integer, // The current number of cars in the lot
        "timestamp": "optional ISO timestamp"  // if not provided, current time will be used
    }
    """
    data = request.get_json()
    lot_id = data.get('lot_id')
    timestamp = data.get('timestamp') or datetime.utcnow().isoformat()

    if not lot_id:
        return jsonify({"message": "Missing required fields: lot_id"}), 400

    car_num = data.get('car_num')
    if car_num is None: # Check if car_num is provided
        return jsonify({"message": "Missing required field: car_num"}), 400

    try:
        # Ensure car_num is an integer
        car_num_int = int(car_num)
    except ValueError:
        return jsonify({"message": "Invalid format for car_num, must be an integer."}), 400

    lot_key = f"parking_lot:{lot_id}"
    redis_client.hset(lot_key, mapping={
        "car_num": car_num_int,
        "update_timestamp": timestamp
    })
    return jsonify({"message": f"Spot data updated in lot {lot_id}"})


###############################################################################
# Retrieving ALL spot statuses for a given LOT from Redis
###############################################################################

@sensor_api.route('/lot_status/<string:lot_id>', methods=['GET'])
def get_lot_status(lot_id):
    """
    Return the aggregated status of a given parking lot from Redis.
    Data is stored in a Redis hash 'parking_lot:<lot_id>'.
    Fields are:
        car_num -> integer (current number of cars)
        update_timestamp -> ISO string (last update time)
        parking_spot_num -> integer (total number of spots in the lot)
    """
    lot_key = f"parking_lot:{lot_id}"
    if not redis_client.exists(lot_key):
        return jsonify({"message": f"Parking lot {lot_id} not found in Redis."}), 404

    lot_data = redis_client.hgetall(lot_key)
    car_num_str = lot_data.get("car_num")
    parking_spot_num_str = lot_data.get("parking_spot_num")

    return jsonify({
        "lot_id": lot_id,
        "car_num": int(car_num_str) if car_num_str is not None else None,
        "update_timestamp": lot_data.get("update_timestamp"),
        "parking_spot_num": int(parking_spot_num_str) if parking_spot_num_str is not None else None
    }), 200

###############################################################################
# Ramp or camera data 
###############################################################################

@sensor_api.route('/update_ramp_status', methods=['POST'])
def update_ramp_status():
    """
    Expects JSON payload:
    {
        "ramp_id": "some_ramp_id",
        "open": true/false,
        "timestamp": "optional ISO timestamp"
    }
    Stores ramp data under a Redis key like 'ramp:<ramp_id>'.
    """
    data = request.get_json()
    ramp_id = data.get('ramp_id')
    open_status = data.get('open')
    timestamp = data.get('timestamp') or datetime.utcnow().isoformat()

    if ramp_id is None or open_status is None:
        return jsonify({"message": "Missing required fields: ramp_id or open_status"}), 400

    redis_client.hmset(f"ramp:{ramp_id}", {
        "open": str(open_status).lower(),
        "last_updated": timestamp
    })
    return jsonify({"message": "Ramp status updated"}), 200

#----------------------------------------------------------------------------------------------------
#   Route Configuration
#----------------------------------------------------------------------------------------------------
def configure_routes(app):
    app.register_blueprint(sensor_api, url_prefix = "/sensor")