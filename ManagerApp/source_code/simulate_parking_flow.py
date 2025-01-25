import os
import time
import random
import requests
import schedule
from datetime import datetime

HOSTNAME = 'parkman.localhost'
BASE_URL_USER = 'http://localhost:8001/user'
BASE_URL_OWNER = 'http://localhost:8001/api'

def get_data(url):
    resp = requests.get(url, headers = {"Host": HOSTNAME})
    if resp.status_code == 200:
        return resp.json()
    else:
        print(f"Failed GET {url}, status {resp.status_code}")
        return None
    
def post_data(url, json_data):
    resp = requests.post(url, json = json_data, headers = {"Host": HOSTNAME})
    return resp

def random_chechout():
    print ("Attempting random checkout...")

    #Pick random user, random lot and random spot
    users_ids = get_data(f"{BASE_URL_OWNER}/users/ALL")
    if not users_ids:
        print("No users found, skipping checkout.")
        return
    user_id = random.choice(users_ids)

    lot_ids = get_data(f"{BASE_URL_OWNER}/parking_lots/ALL")
    if not lot_ids:
        print("No parking lots found, skipping checkout.")
        return
    lot_id = random.choice(lot_ids)

    spots_list = get_data(f"{BASE_URL_OWNER}/parking_spots/ALL")
    if not spots_list:
        print("No parking spots found, skipping checkout.")
        return

    #Filter only spots from a chosen random lot
    spots_same_lot = [s for s in spots_list if s["parking_lot"] == lot_id]
    if not spots_same_lot:
        print("No parking spots belog to lot {lot_id}, skipping checkout.") 
        return
    
    random_spot = random.choice(spots_same_lot)
    spot_id = random_spot["_id"]

    #Now that we have a spot, call checkout
    checkout_data = {
        "id_parking_lot": lot_id,
        "id_parking_spot": spot_id,
        "id_user": user_id
    }
    resp = post_data(f"{BASE_URL_USER}/checkout", checkout_data)
    if resp.status_code == 200:
        print(f"Checkout success for user={user_id}, lot={lot_id}, spot={spot_id}")
        print("Response =>", resp.json())
    else:
        print(f"Checkout attempt failed: {resp.status_code} => {resp.text}")

def random_reserve():
    print ("Attempting random reserve...")

    users_ids = get_data(f"{BASE_URL_OWNER}/users/ALL")
    if not users_ids:
        print("No users found, skipping reserve.")
        return
    user_id = random.choice(users_ids)

    spots_list = get_data(f"{BASE_URL_OWNER}/parking_spots/ALL")
    if not spots_list:
        print("No parking spots found, skipping checkout.")
        return
    
    random_spot = random.choice(spots_list)
    spot_id = random_spot["_id"]
    lot_id = random_spot["parking_lot"]

    reserve_data = {
        "id_user": user_id,
        "id_parking_lot": lot_id,
        "id_parking_spot": spot_id
    }
    resp = post_data(f"{BASE_URL_USER}/reserve", reserve_data)
    if resp.status_code in [200, 201]:
        print("Reservation success =>", resp.json())
    else:
        print(f"Reservation attempt failed: {resp.status_code} => {resp.text}")

def scheduled_job():
    coin = random.randint(0, 1)
    if coin < 0.5:
        random_reserve()
    else:
        random_chechout()

def main():
    schedule.every(3).seconds.do(scheduled_job)

    print("Reservations/Checkouts started.")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()