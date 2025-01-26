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
        "lot_id": "123"
        "spot_id": "A1",
        "occupied": true/false,
        "timestamp": "optional ISO timestamp"  // if not provided, current time will be used
    }
    """
    data = request.get_json()
    lot_id = data.get('lot_id')
    spot_id = data.get('spot_id')
    occupied = data.get('occupied')
    timestamp = data.get('timestamp') or datetime.utcnow().isoformat()

    if not lot_id or not spot_id or not occupied:
        return jsonify({"message": "Missing required fields: lot_id, spot_id or occupied"}), 400
    
    #Convert booleans to 'true'/'false'
    occupied_str = 'true' if occupied else 'false'

    lot_key = f"parking_lot:{lot_id}"
    
    #Set the status in the lot's hash
    redis_client.hset(lot_key, f"spot_{spot_id}", occupied_str)
    redis_client.hset(lot_key, f"spot_{spot_id}_last_update", timestamp)

    return jsonify({"message": f"Spot {spot_id} updated in lot {lot_id}"})

###############################################################################
# Retrieving ALL spot statuses for a given LOT from Redis
###############################################################################

@sensor_api.route('/lot_status/<string:lot_id>', methods=['GET'])
def get_lot_status(lot_id):
    """
    Return the status (occupied/free) of all spots in a given lot.
    Data is assumed to be stored in a Redis hash 'parking_lot:<lot_id>'.
    Fields are:
        spot_<spot_id> -> "true"/"false"
        spot_<spot_id>_last_update -> <timestamp>
    """
    lot_key = f"parking_lot:{lot_id}"
    if not redis_client.exists(lot_key):
        return jsonify({"message": f"Parking lot {lot_id} not found."})
    
    spot_data = redis_client.hgetall(lot_key)
    """
    Example of spot_data:
    {
        "spot_A1": "true",
        "spot_A1_last_update": "2025-01-21T13:45:00Z",
        "spot_B3": "false",
        "spot_B1_last_update": "2025-01-21T13:50:00Z",
        ...
    }
    """
    aggregated_spots = {}
    for field, value in spot_data.items():
        if field.startswith("spot_"):
        # Split by '_' => ["spot", "<spot_id>"] or ["spot", "<spot_id>", "last_update"]
            parts = field.split("_", 2)
            if len(parts) == 2:
                # e.g. field = "spot_A1" => parts = ["spot", "A1"]
                s_id = parts[1]
                if s_id not in aggregated_spots:
                    aggregated_spots[s_id] = {"occupied": None, "last_update": None}
                aggregated_spots[s_id]["occupied"] = value
            elif len(parts) == 3:
                # e.g. field = "spot_A1_last_update"
                s_id = parts[1]
                if s_id not in aggregated_spots:
                    aggregated_spots[s_id] = {"occupied": None, "last_update": None}
                aggregated_spots[s_id]["last_update"] = value
    
    return jsonify({
        "lot_id": lot_id,
        "spots": aggregated_spots
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