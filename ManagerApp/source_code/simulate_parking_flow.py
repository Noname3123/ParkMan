import os
import time
import random
import requests
import schedule
from psycopg2 import connect 
from psycopg2.extras import RealDictCursor
from datetime import datetime
import threading

HOSTNAME = 'parkman.localhost'
BASE_URL_USER = 'http://localhost:8001/user'
BASE_URL_OWNER = 'http://localhost:8001/api'


def get_users_from_timescale():

    TIMESCALE_DB_URI="postgresql://postgres_user:postgres_pass@localhost:5432/ParkingTransactionsDB"
    timescale_conn=connect(TIMESCALE_DB_URI)
    timescale_cursor=timescale_conn.cursor(cursor_factory=RealDictCursor)

    ##get all data from timescale fitting range:
    query_timescale = """
        SELECT user_id, parking_lot_id FROM parking_transactions WHERE
        exit_timestamp IS NULL;
    """
    timescale_cursor.execute(query_timescale)
    data_timescale = timescale_cursor.fetchall()

    timescale_cursor.close()
    
    return list(set((entry['user_id']) for entry in data_timescale))
    
def get_lot_for_user(user_id):

    TIMESCALE_DB_URI="postgresql://postgres_user:postgres_pass@localhost:5432/ParkingTransactionsDB"
    timescale_conn=connect(TIMESCALE_DB_URI)
    timescale_cursor=timescale_conn.cursor(cursor_factory=RealDictCursor)

    ##get all data from timescale fitting range:
    query_timescale = """
        SELECT parking_lot_id FROM parking_transactions WHERE
        exit_timestamp IS NULL AND user_id=%s;
    """
    timescale_cursor.execute(query_timescale, (user_id,))
    data_timescale = timescale_cursor.fetchall()

    timescale_cursor.close()
    
    return list(set((entry['parking_lot_id']) for entry in data_timescale))
    


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
    #users_ids = get_data(f"{BASE_URL_OWNER}/users/ALL")
    users_ids=get_users_from_timescale() #NOTE: dodao ovo da se spriječi users have no active reservation i problem s parking lotovima koji nisu na rezervaciji
    if not users_ids:
        print("No users found, skipping checkout.")
        return
    user_id = random.choice(users_ids)

    lot_ids = get_lot_for_user(user_id)
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

    print(checkout_data)

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
    def run_scheduler():
        schedule.every(3).seconds.do(scheduled_job)
        while True:
            schedule.run_pending()
            time.sleep(1)

    print("Reservations/Checkouts started.")
    for _ in range(4):  # Number of threads
        t = threading.Thread(target=run_scheduler)
        t.start()

if __name__ == "__main__":
    main()