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
    url = f"http://{MANAGER_HOST}:{MANAGER_PORT}/api/parking_lots/ALL"
    print(f"Fetching parking lots from {url}...")
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

def fetch_parking_spots():
    #Fetch all parking spots for a given parking lot from the Manager API
    url = f"http://{MANAGER_HOST}:{MANAGER_PORT}/api/parking_spots/ALL"
    print(f"Fetching parking spots from {url}...")
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

def fetch_sensor_data(lot_id):
    #Fetch latest sensor data for a parking lot from the Sensor API
    url = f"http://{SENSOR_HOST}:{SENSOR_PORT}/sensor/lot_status/{lot_id}"
    print(f"Fetching sensor data for lot {lot_id} from {url}...")
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

def initialize_lot_and_spots(redis_client, lot_id, all_spots):
    #Initialize parking lot and its spots in Redis
    lot_key = f"parking_lot:{lot_id}"
    if not redis_client.exists(lot_key):
        redis_client.hset(lot_key, "init_placeholder", "false")
        print(f"Initialized lot: {lot_key}")

    spots = [spot for spot in all_spots if spot["parking_lot"] == lot_id]
    for spot in spots:
        spot_id = spot["_id"]
        occupied = "false" #Default spot status
        timestamp = datetime.utcnow().isoformat()

        redis_client.hset(lot_key, f"spot_{spot_id}", occupied)
        redis_client.hset(lot_key, f"spot_{spot_id}_last_update", timestamp) 

        print(f"Initialized spot {spot_id} for lot {lot_id}.")

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
    all_spots = fetch_parking_spots()

    #2. Initialize parking lots and spots in Redis
    for lot_id in parking_lots:
        initialize_lot_and_spots(redis_client, lot_id, all_spots)

    #3. Update spot statuses using Sensor API
    for lot_id in parking_lots:
        update_spot_statuses(redis_client, lot_id)

    print(f"Finished Redis init.")

if __name__ == "__main__":
    main()
