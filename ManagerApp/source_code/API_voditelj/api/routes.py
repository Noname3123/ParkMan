from flask import request, jsonify, Blueprint
from pymongo import MongoClient
import os
from dotenv import load_dotenv

api = Blueprint('api', __name__)

#----------------------------------------------------------------------------------------------------
#   Setting Up MongoDB
#----------------------------------------------------------------------------------------------------

#Loading the environment variables
load_dotenv()

#MongoDB Configuration
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://user_Park_Manager:mongo_pass@mongo_manager_db_service:27016/ParkMan_manager_db")
client = MongoClient(MONGO_URI)
db = client.get_database()

#MongoDB Collections
owners_collection = db.owners
parking_lots_collection = db.parking_lots
parking_spots_collection = db.parking_spots

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
    owner = owners_collection.find_one({"_id": owner_id}, {"_id: 0"}) #{"_id: 0"} - Exclude the ID of the owner when outputing results
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
        "parking_spaces": [] #Empty list for storing newly added parking spaces
    }
    result = parking_lots_collection.insert_one(parking_lot)
    #Adding this parking lot to its owner
    if data.get('owner_id'):
        owners_collection.update_one(
            {"_id": data['owner_id']},
            {"$push": {"parking_lots": result.inserted_id}}
        )
    return jsonify({"message": "Parking lot added", "id": str(result.inserted_id)}), 201

@api.route('/parking_lots/<string:lot_id>', methods = ['GET']) #Defining URL for getting existing parking lots
def get_parking_lot(lot_id):
    parking_lot = parking_lots_collection.find_one({"_id": lot_id}, {"_id": 0}) #{"_id: 0"} - Exclude the ID of the owner when outputing result
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
        {"_id": data['parking_lot']},
        {"$push": {"parking_spaces": result.inserted_id}}
    )
    return jsonify({"message": "Parking spot added", "id": str(result.inserted_id)}), 201

@api.route('/parking_lots/<string:spot_id>', methods = ['GET']) #Defining URL for getting existing parking spots
def get_parking_spot(spot_id):
    parking_spot = parking_spots_collection.find_one({"_id": spot_id}, {"_id": 0})
    if parking_spot:
        return jsonify(parking_spot)
    else:
        return jsonify({"message": "Parking spot not found"}), 404
    
#----------------------------------------------------------------------------------------------------
#   Route Configuration
#----------------------------------------------------------------------------------------------------

def configure_routes(app):
    app.register_blueprint(api, url_prefix='/api')