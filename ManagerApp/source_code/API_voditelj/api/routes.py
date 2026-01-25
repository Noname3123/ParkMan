from flask import request, jsonify, Blueprint
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from bson import ObjectId
from datetime import datetime # Added for timestamping
from minio import Minio # Added for MinIO integration
from minio.error import S3Error # Added for MinIO error handling
from minio.lifecycleconfig import LifecycleConfig, Rule, Expiration
from minio.commonconfig import Filter # Added for MinIO lifecycle
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
#   Setting Up MinIO
#----------------------------------------------------------------------------------------------------

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9901") # Default if not in Docker or .env
APP_MINIO_ACCESS_KEY = os.getenv("APP_MINIO_ACCESS_KEY", "apivoditeljuser")
APP_MINIO_SECRET_KEY = os.getenv("APP_MINIO_SECRET_KEY", "apivoditeljuserPass")  
MINIO_SECURE = os.getenv("MINIO_SECURE", "False").lower() == "true"

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=APP_MINIO_ACCESS_KEY,
    secret_key=APP_MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)

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
    result=owners_collection.insert_one(owner)
    return jsonify({"message": "Owner added","id": str(result.inserted_id)}), 201

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
        "parking_spaces": [], # Empty list for storing newly added parking spaces
        "camera_info": [],    # Initialize camera_info as an empty list
        "minio_safe_data_storage": None, # Initialize minio_safe_data_storage as None
        "minio_camera_images_bucket": None # Initialize minio_camera_images_bucket as None
    }
    result = parking_lots_collection.insert_one(parking_lot)
    lot_id_obj = result.inserted_id
    lot_id_str = str(lot_id_obj)

    # --- MinIO Bucket Creation for safe_data_storage ---
    bucket_name = f"safe-storage-parking-lot-{lot_id_str}"
    minio_status_message = ""
    minio_bucket_linked = False
    try:
        # Define the lifecycle configuration using MinIO SDK objects
        lifecycle_rule= Rule(
                status="Enabled",
                rule_filter=Filter(prefix=""),  # Apply to all objects in the bucket
                rule_id="DefaultExpireAfter30Days",
                expiration=Expiration(days=30)
            )
        config = LifecycleConfig([lifecycle_rule])
        
        

        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)
            minio_status_message = f"MinIO bucket '{bucket_name}' created."
        else:
            minio_status_message = f"MinIO bucket '{bucket_name}' already exists."
        
        # Link the bucket in the parking lot document
        update_result = parking_lots_collection.update_one(
            {"_id": lot_id_obj},
            {"$set": {"minio_safe_data_storage": bucket_name}}
        )
        if update_result.modified_count > 0 or update_result.matched_count > 0 : # Check if linked or already linked
            minio_bucket_linked = True
            minio_status_message += " Successfully linked to parking lot."
            try:
                # Always try to set/update lifecycle policy
                minio_client.set_bucket_lifecycle(bucket_name, config)
                minio_status_message += " Default 30-day lifecycle policy applied."
            except S3Error as s3_lc_error:
                minio_status_message += f" WARNING: Failed to apply lifecycle policy to '{bucket_name}': {str(s3_lc_error)}."
        else: # Should not happen if insert_one was successful
            minio_status_message += " Failed to link bucket in database."
    except S3Error as e:
       minio_status_message = f"WARNING: MinIO bucket '{bucket_name}' creation/linking failed: {str(e)}. 'minio_safe_data_storage' remains unlinked."
    except Exception as e: # Catch other potential errors during MinIO interaction
       minio_status_message = f"WARNING: An unexpected error occurred during MinIO setup for bucket '{bucket_name}': {str(e)}. 'minio_safe_data_storage' remains unlinked."
    # --- End MinIO Bucket Creation ---

    # --- MinIO Bucket Creation for camera-images ---
    camera_images_bucket = f"camera-images-parking-lot-{lot_id_str}"
    try:
        if not minio_client.bucket_exists(camera_images_bucket):
            minio_client.make_bucket(camera_images_bucket)
            minio_status_message += f" Bucket '{camera_images_bucket}' created."
        
        parking_lots_collection.update_one(
            {"_id": lot_id_obj},
            {"$set": {"minio_camera_images_bucket": camera_images_bucket}}
        )
    except Exception as e:
        minio_status_message += f" Failed to setup '{camera_images_bucket}': {str(e)}."

    #Adding this parking lot to its owner
    if data.get('owner_id'):
        owners_collection.update_one(
            {"_id": ObjectId(data['owner_id'])},
            {"$push": {"parking_lots": result.inserted_id}}
        )

    #Create a Redis hash for the new parking lot, with a placeholder
    lot_key = f"parking_lot:{lot_id_str}"
    timestamp = datetime.utcnow().isoformat()

    redis_client.hset(lot_key, mapping={
        "car_num": 0,  # New lots start with 0 cars
        "update_timestamp": timestamp,
        "parking_spot_num": 0  # New lots start with 0 parking spots
    })

    response_message = "Parking lot added"
    response_details = {"id": lot_id_str}

    if minio_bucket_linked:
        response_details["minio_bucket_name"] = bucket_name
    response_details["minio_camera_images_bucket"] = camera_images_bucket
    response_details["minio_status"] = minio_status_message

    return jsonify({"message": response_message, "details": response_details}), 201

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
        # Fetch without projection first to handle complex types, then apply projection if needed (or remove it)
        # For consistency with other GET routes, keep the {"_id": 0} projection.
        parking_lot_doc = parking_lots_collection.find_one({"_id": ObjectId(lot_id)})
        if parking_lot_doc:
            parking_lot = parking_lot_doc.copy() # Work on a copy
            del parking_lot["_id"] # Apply the exclusion of _id

            parking_lot["parking_spaces"]=[str(id) for id in parking_lot.get("parking_spaces", [])]
            if "camera_info" in parking_lot and parking_lot["camera_info"]:
                for camera in parking_lot["camera_info"]:
                    if "camera_id" in camera and isinstance(camera["camera_id"], ObjectId):
                        camera["camera_id"] = str(camera["camera_id"])
    
    if parking_lot:
        return jsonify(parking_lot)
    else:
        return jsonify({"message": "Parking lot not found"}), 404

#----------------------------------------------------------------------------------------------------
#   Parking Lot Camera Routes
#----------------------------------------------------------------------------------------------------

@api.route('/parking_lots/<string:lot_id>/cameras', methods=['POST'])
def add_camera_to_parking_lot(lot_id):
    data = request.get_json()
    if not data or not data.get('camera_name') or not data.get('camera_link'):
        return jsonify({"message": "Missing required fields: camera_name or camera_link"}), 400

    try:
        object_lot_id = ObjectId(lot_id)
    except Exception:
        return jsonify({"message": "Invalid parking lot ID format"}), 400

    parking_lot = parking_lots_collection.find_one({"_id": object_lot_id})
    if not parking_lot:
        return jsonify({"message": "Parking lot not found"}), 404

    new_camera_id = ObjectId()
    camera_data = {
        "camera_id": new_camera_id,
        "camera_name": data['camera_name'],
        "camera_link": data['camera_link'] # As per spec, all cameras ref to same bucket (link is the ref string)
    }

    result = parking_lots_collection.update_one(
        {"_id": object_lot_id},
        {"$push": {"camera_info": camera_data}}
    )

    if result.modified_count:
        return jsonify({"message": "Camera added to parking lot", "camera_id": str(new_camera_id)}), 201
    else:
        return jsonify({"message": "Failed to add camera"}), 500

@api.route('/parking_lots/<string:lot_id>/cameras/<string:camera_id>', methods=['DELETE'])
def remove_camera_from_parking_lot(lot_id, camera_id):
    try:
        object_lot_id = ObjectId(lot_id)
        object_camera_id = ObjectId(camera_id)
    except Exception:
        return jsonify({"message": "Invalid ID format for parking lot or camera"}), 400

    result = parking_lots_collection.update_one(
        {"_id": object_lot_id},
        {"$pull": {"camera_info": {"camera_id": object_camera_id}}}
    )

    if result.modified_count:
        return jsonify({"message": "Camera removed from parking lot"}), 200
    else:
        # Could be lot not found, or camera not found in lot
        parking_lot = parking_lots_collection.find_one({"_id": object_lot_id})
        if not parking_lot:
            return jsonify({"message": "Parking lot not found"}), 404
        return jsonify({"message": "Camera not found in parking lot or no change made"}), 404

@api.route('/parking_lots/<string:lot_id>/cameras/<string:camera_id>', methods=['PUT'])
def modify_camera_in_parking_lot(lot_id, camera_id):
    data = request.get_json()
    if not data:
        return jsonify({"message": "No data provided for update"}), 400

    try:
        object_lot_id = ObjectId(lot_id)
        object_camera_id = ObjectId(camera_id)
    except Exception:
        return jsonify({"message": "Invalid ID format for parking lot or camera"}), 400

    update_fields = {}
    if 'camera_name' in data:
        update_fields['camera_info.$[elem].camera_name'] = data['camera_name']
    if 'camera_link' in data:
        update_fields['camera_info.$[elem].camera_link'] = data['camera_link']

    if not update_fields:
        return jsonify({"message": "No fields to update provided"}), 400

    result = parking_lots_collection.update_one(
        {"_id": object_lot_id, "camera_info.camera_id": object_camera_id},
        {"$set": update_fields},
        array_filters=[{"elem.camera_id": object_camera_id}]
    )

    if result.matched_count == 0: # Check matched_count first
        return jsonify({"message": "Parking lot or camera not found"}), 404
    if result.modified_count:
        return jsonify({"message": "Camera updated successfully"}), 200
    else:
        return jsonify({"message": "Camera data is the same, no update performed"}), 200 # Or 304 Not Modified

@api.route('/parking_lots/<string:lot_id>/safe_storage', methods=['POST'])
def create_safe_data_storage(lot_id):
    try:
        object_lot_id = ObjectId(lot_id)
    except Exception:
        return jsonify({"message": "Invalid parking lot ID format"}), 400

    bucket_name = f"safe-storage-parking-lot-{lot_id}"

    try:
        # Define the lifecycle configuration using MinIO SDK objects
        
        lifecyce_rule=Rule(
                status="Enabled",
                rule_filter=Filter(prefix=""),  # Apply to all objects in the bucket
                rule_id="DefaultExpireAfter30Days",
                expiration=Expiration(days=30)
            )
        
        config = LifecycleConfig([lifecyce_rule])

        lifecycle_applied_message = ""

        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)
        
        # Set or update the lifecycle policy
        minio_client.set_bucket_lifecycle(bucket_name, config)
        lifecycle_applied_message = " Default 30-day lifecycle policy applied/updated."
        
        parking_lots_collection.update_one(
            {"_id": object_lot_id},
            {"$set": {"minio_safe_data_storage": bucket_name}}
        )
        return jsonify({"message": f"Safe data storage created and linked.{lifecycle_applied_message}", "bucket_name": bucket_name}), 201
    except S3Error as e:
        # Check if the error is because the lifecycle already exists and is identical, which can be ignored.
        return jsonify({"message": f"MinIO error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"message": f"An unexpected error occurred: {str(e)}"}), 500

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

    # Increment the parking_spot_num in Redis for this lot
    lot_key = f"parking_lot:{data['parking_lot']}"
    redis_client.hincrby(lot_key, "parking_spot_num", 1)

    # Update the timestamp for the lot as its structure has changed
    timestamp = datetime.utcnow().isoformat()
    redis_client.hset(lot_key, "update_timestamp", timestamp)

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
        spot["_id"] = str(spot["_id"]) # Corrected 's' to 'spot'
        spot["parking_lot"] = str(spot["parking_lot"]) # Corrected 's' to 'spot'
        return jsonify(spot)
    else:
        return jsonify({"message": "Parking spot not found"}), 404
    
#----------------------------------------------------------------------------------------------------
#   Route Configuration
#----------------------------------------------------------------------------------------------------

def configure_routes(app):
    app.register_blueprint(api, url_prefix='/api')