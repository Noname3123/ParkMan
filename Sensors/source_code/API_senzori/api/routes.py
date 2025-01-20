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

#Endpoint to update occupancy status of a parking spot
@sensor_api.route('/update_spot_status', methods=['POST'])
def update_spot_status():
    """
    Expects JSON payload:
    {
        "spot_id": "some_spot_id",
        "occupied": true/false,
        "timestamp": "optional ISO timestamp"  // if not provided, current time will be used
    }
    """
    data = request.get_json()
    spot_id = data.get('spot_id')
    occupied = data.get('occupied')
    timestamp = data.get('timestamp') or datetime.utcnow().isoformat()

    if spot_id is None or occupied is None:
        return jsonify({"message": "Missing required fields: spot_id or occupied"}), 400
    
    #Save status in Redis
    redis_client.hmset(f"spot:{spot_id}", {"occupied": occupied, "last_update": timestamp})
    return jsonify({"message": "Spot status updated"}), 200

#Endpoint to get occupancy status of a parking spot
@sensor_api.route('/get_spot_status/<string:spot_id>', methods=['GET'])
def get_spot_status(spot_id):
    #Retrieve spot status from Redis
    spot_key = f"spot:{spot_id}"
    if not redis_client.exists(spot_key):
        return jsonify({"message": "Spot not found"}), 404
    
    status = redis_client.hgetall(spot_key)
    return jsonify({
        "spot_id": spot_id,
        "occupied": status.get("occupied"),
        "last_updated": status.get("last_updated")
    }), 200

#Endpoint to update ramp or camera data, if necessary
@sensor_api.route('/update_ramp_status', methods=['POST'])
def update_ramp_status():
    """
    Expects JSON payload:
    {
        "ramp_id": "some_ramp_id",
        "open": true/false,
        "timestamp": "optional ISO timestamp"
    }
    """
    data = request.get_json()
    ramp_id = data.get('ramp_id')
    open_status = data.get('open')
    timestamp = data.get('timestamp') or datetime.utcnow().isoformat()

    if ramp_id is None or open_status is None:
        return jsonify({"message": "Missing required fields: ramp_id or open_status"}), 400
    
    redis_client.hmset(f"ramp:{ramp_id}", {"open": open_status, "last_updated": timestamp})
    return jsonify({"message": "Ramp status updated"}), 200

#----------------------------------------------------------------------------------------------------
#   Route Configuration
#----------------------------------------------------------------------------------------------------
def configure_routes(app):
    app.register_blueprint(sensor_api, url_prefix = "/sensor")