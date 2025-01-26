from flask import request, jsonify, Blueprint
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from bson import ObjectId
import redis

api = Blueprint('api', __name__)

#----------------------------------------------------------------------------------------------------
#   Setting Up MongoDB
#----------------------------------------------------------------------------------------------------

#Loading the environment variables
load_dotenv()

#MongoDB Configuration
MONGO_URI = os.getenv("MONGO_MANAGER_DATABASE_URI", "mongodb://user_Park_Manager:mongo_pass@localhost:27016/ParkMan_manager_db") #if not in docker, replace service name with localhost
client = MongoClient(MONGO_URI)
db = client.get_database()

MONGO_EXTERNAL=os.getenv("MONGO_USER_DATABASE_R_ONLY_URI", "mongodb://external:external_pass@localhost:27017/ParkMan_user_db")
external_client=MongoClient(MONGO_EXTERNAL)
db_external=external_client.get_database()

#MongoDB Collections
owners_collection = db.owners
parking_lots_collection = db.parking_lots
parking_spots_collection = db.parking_spots
users_collection=db_external.users

#----------------------------------------------------------------------------------------------------
#   Setting Up Redis
#----------------------------------------------------------------------------------------------------

REDIS_HOST = os.getenv("REDIS_HOST", "redis_parking_spots_status")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.StrictRedis(host = REDIS_HOST, port = REDIS_PORT, decode_responses = True)

#----------------------------------------------------------------------------------------------------
#   Owner Routes
#----------------------------------------------------------------------------------------------------

@api.route('/owners', methods = ['POST']) #Defining URL for adding new owners
def add_owner():
    data = request.get_json()
    if not data.get('name') or not data.get('surname'):
        return jsonify({"message": "Missing required fields: name or surname"}), 400
    
    owner = {
        "name": data['name'],
        "surname": data['surname'],
        "parking_lots": [] #Empty list for storing newly added parking lots
    }
    owners_collection.insert_one(owner)
    return jsonify({"message": "Owner added"}), 201

@api.route('/owners/<string:owner_id>', methods = ['GET']) #Defining URL for getting existing owners
def get_owner(owner_id):
    owner=None
    if owner_id =="ALL":
         #Get all owner ids if id code == ALL
        owner =[str(id) for id in owners_collection.distinct('_id')]
    else:
        owner = owners_collection.find_one({"_id": ObjectId(owner_id)}, {"_id: 0"}) #{"_id: 0"} - Exclude the ID of the owner when outputing results
    if owner:
        return jsonify(owner)
    else:
        return jsonify({"message": "Owner not found"}), 404
    
#----------------------------------------------------------------------------------------------------
#   Parking Lot Routes
#----------------------------------------------------------------------------------------------------

@api.route('/parking_lots', methods = ['POST']) #Defining URL for adding new parking lots
def add_parking_lot():
    data = request.get_json()
    if not data.get('name') or not data.get('geolocation'):
        return jsonify({"message": "Missing required fields: name or geolocation"}), 400
    
    parking_lot = {
        "name": data['name'],
        "geolocation": data['geolocation'],
        "parking_spaces": [] # Empty list for storing newly added parking spaces
    }
    result = parking_lots_collection.insert_one(parking_lot)
    #Adding this parking lot to its owner
    if data.get('owner_id'):
        owners_collection.update_one(
            {"_id": ObjectId(data['owner_id'])},
            {"$push": {"parking_lots": result.inserted_id}}
        )

    #Create a Redis hash for the new parking lot, with a placeholder
    lot_id_str = str(result.inserted_id)
    lot_key = f"parking_lot:{lot_id_str}"

    redis_client.hset(lot_key, "false", "false")

    return jsonify({"message": "Parking lot added", "id": lot_id_str}), 201

#define get_users API route (so that manager can see info about users)
@api.route('/users/<string:user_id>', methods = ['GET']) #Defining URL for getting existing owners
def get_user(user_id):
    user=None
    if user_id =="ALL":
         #Get all user ids if id code == ALL
        user =[str(id) for id in users_collection.distinct('_id')]
    else:
        user = users_collection.find_one({"_id": ObjectId(user_id)}, {"_id: 0"}) #{"_id: 0"} - Exclude the ID of the owner when outputing results
    if user:
        return jsonify(user)
    else:
        return jsonify({"message": "Owner not found"}), 404


@api.route('/parking_lots/<string:lot_id>', methods = ['GET']) #Defining URL for getting existing parking lots
def get_parking_lot(lot_id):
    parking_lot=None
    if lot_id=="ALL": #if search term is "ALL" => give id's of all lots
        parking_lot =[str(id) for id in parking_lots_collection.distinct('_id')]
    else:
        parking_lot = parking_lots_collection.find_one({"_id": ObjectId(lot_id)}, {"_id": 0}) #{"_id: 0"} - Exclude the ID of the owner when outputing result
    if parking_lot:
        return jsonify(parking_lot)
    else:
        return jsonify({"message": "Parking lot not found"}), 404

#----------------------------------------------------------------------------------------------------
#   Parking Spot Routes
#----------------------------------------------------------------------------------------------------

@api.route('/parking_spots', methods = ['POST']) #Defining URL for adding new parking spots
def add_parking_spot():
    data = request.get_json()
    if not data.get('parking_lot') or not data.get('spot_price'):
        return jsonify({"message": "Missing required fields: parking_lot or spot_price"})
    
    parking_spot = {
        "parking_lot": data['parking_lot'],
        "spot_price": data['spot_price']
    }
    result = parking_spots_collection.insert_one(parking_spot)
    #Adding this parking spot to its parking lot 
    parking_lots_collection.update_one(
        {"_id": ObjectId(data['parking_lot'])},
        {"$push": {"parking_spaces": result.inserted_id}}
    )

    #Add a new field in Redis for this spot, making occupancy as "false"
    lot_key = f"parking_lot:{data['parking_lot']}"
    spot_id_str = str(result.inserted_id)

    redis_client.hset(lot_key, f"spot_{spot_id_str}", "false")

    return jsonify({"message": "Parking spot added", "id": str(result.inserted_id)}), 201

@api.route('/parking_spots/<string:spot_id>', methods = ['GET']) #Defining URL for getting existing parking spots
def get_parking_spot(spot_id):
    if spot_id == "ALL":
        spots = []
        for s in parking_spots_collection.find({}):
            s["_id"] = str(s["_id"])
            s["parking_lot"] = str(s["parking_lot"])
            spots.append(s)
        return jsonify(spots)
    
    spot = parking_spots_collection.find_one({"_id": ObjectId(spot_id)})
    if spot:
        spot["_id"] = str(s["_id"])
        spot["parking_lot"] = str(s["parking_lot"])
        return jsonify(spot)
    else:
        return jsonify({"message": "Parking spot not found"}), 404
    
#----------------------------------------------------------------------------------------------------
#   Route Configuration
#----------------------------------------------------------------------------------------------------

def configure_routes(app):
    app.register_blueprint(api, url_prefix='/api')