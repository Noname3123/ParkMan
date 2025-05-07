import os
import requests
import redis
from datetime import datetime

MANAGER_HOST = os.getenv("MANAGER_HOST", "manager_app")
MANAGER_PORT = os.getenv("MANAGER_PORT", "80")
SENSOR_HOST = os.getenv("SENSOR_HOST", "sensor_app")
SENSOR_PORT = os.getenv("SENSOR_PORT", "80")

REDIS_HOST = os.getenv("REDIS_HOST", "redis_parking_spots_status")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

def fetch_parking_lots():
    #Fetch all parking lot IDs from the Manager API

    try:
        url = f"http://{MANAGER_HOST}:{MANAGER_PORT}/api/parking_lots/ALL"
        print(f"Fetching parking lots from {url}...")
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching parking lots from {url}: {e}")
        return None
    
def fetch_parking_lot(lot_id):
    #Fetch all parking lot IDs from the Manager API

    try:
        url = f"http://{MANAGER_HOST}:{MANAGER_PORT}/api/parking_lots/{lot_id}"
        print(f"Fetching parking lots from {url}...")
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching parking lots from {url}: {e}")
        return None


def get_parking_spot_number(lot_id):
    parking_lot= fetch_parking_lot(lot_id)
    if parking_lot:
        parking_spot_ids= parking_lot.get("parking_spaces")
        if parking_spot_ids:
            return len(parking_spot_ids)
    return None


def fetch_parking_spots():
    #Fetch all parking spots for a given parking lot from the Manager API
    try:
        url = f"http://{MANAGER_HOST}:{MANAGER_PORT}/api/parking_spots/ALL"
        print(f"Fetching parking spots from {url}...")
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching parking spots from {url}: {e}")
        return None
    

    

def fetch_sensor_data(lot_id):
    #Fetch latest sensor data for a parking lot from the Sensor API
    try:
        url = f"http://{SENSOR_HOST}:{SENSOR_PORT}/sensor/lot_status/{lot_id}"
        print(f"Fetching sensor data for lot {lot_id} from {url}...")
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching sensor data for lot {lot_id} from {url}: {e}")
        return None
    


    

def initialize_lot_data(redis_client, lot_id):
    #Initialize parking lot data in Redis with car_num and update_timestamp
    lot_key = f"parking_lot:{lot_id}"
    timestamp = datetime.utcnow().isoformat()

    # Delete the key to ensure it's clean before setting new schema fields
    redis_client.delete(lot_key)

    park_spot_num=get_parking_spot_number(lot_id)

    # Set car_num and update_timestamp
    # Redis stores values as strings; redis-py handles conversion for numbers.
    # Explicitly using 0 for car_num.
    redis_client.hset(lot_key, mapping={
        "car_num": 0,
        "update_timestamp": timestamp,
        "parking_spot_num": park_spot_num
    })
    print(f"Initialized data for lot {lot_key}: car_num=0, update_timestamp={timestamp}, parking_spot_num={park_spot_num}")

def update_spot_statuses(redis_client, lot_id):
    #Update spot statuses in Redis using the Sensor API data
    lot_key = f"parking_lot:{lot_id}"
    try:
        sensor_data = fetch_sensor_data(lot_id)
        for spot_id, spot_data in sensor_data["spots"].items():
            occupied = spot_data["occupied"]
            timestamp = spot_data["last_update"]

            redis_client.hset(lot_key, f"spot_{spot_id}", occupied)
            redis_client.hset(lot_key, f"spot_{spot_id}_last_update", timestamp)

            print(f"Updated spot {spot_id} in lot {lot_id} with sensor data.")
    except Exception as e:
        print(f"Failed to update spot statuses for lot {lot_id}: {e}")

def main():
    redis_client = redis.Redis(host = REDIS_HOST, port = REDIS_PORT, decode_responses = True)

    #1. Fetch all parking lots
    parking_lots = fetch_parking_lots()
    # fetch_parking_spots() is no longer needed as we are not initializing individual spots.

    #If fetching parking lots failed or no lots are available
    if not parking_lots: # Checks for None or an empty list
        print("No parking lots fetched or parking lots list is empty. Exiting.")
        return

    #2. Initialize parking lots in Redis with the new schema
    for lot_id in parking_lots:
        initialize_lot_data(redis_client, lot_id)

    # Step 3 (Update spot statuses using Sensor API) is removed because
    # its current implementation conflicts with the new schema for parking_lot:{lot_id}.
    # This script now focuses solely on initialization with the specified schema.

    print("Finished Redis initialization with the new schema.")

if __name__ == "__main__":
    main()
