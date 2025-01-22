from faker import Faker
import requests
from datetime import datetime, timedelta
import random

fake = Faker()

hostname='parkman.localhost' #NOTE: added hostname due to traefik communication rule Host(parkman.localhost - which is the name of nginx service in docker-compose)

base_url_user = 'http://localhost:8001/user' #traefik routes from 8001 to 80, since generate data runs outside of containers on this machine - use localhost
base_url_owner = 'http://localhost:8001/api'

#----------------------------------------------------------------------------------------------------
#   Data Generation
#----------------------------------------------------------------------------------------------------

def generate_users(n):
    users = [{
        "name": fake.first_name(),
        "surname": fake.last_name(),
        "car_registration": [fake.license_plate() for _ in range(random.randint(1, 3))],
        "home_geolocation": [float(fake.latitude()), float(fake.longitude())], #changed to float - JSON doesnt support decimal format

    } for _ in range(n)]
    return users

def generate_owners(n):
    owners = [{
        "name": fake.first_name(),
        "surname": fake.last_name()
    } for _ in range(n)]
    return owners

def generate_parking_lots(n, owners):
    parking_lots = [{
        "name": fake.company(),
        "geolocation": [float(fake.latitude()), float(fake.longitude())], #changed to float - JSON doesnt support decimal format
        "owner_id": random.choice(owners) #Add this parking lot to a random owner
    } for _ in range(n)]
    return parking_lots

def generate_parking_spots(n, parking_lots):
    parking_spots = [{
        "parking_lot": random.choice(parking_lots), #Add this parking spot to a random parking lot
        "spot_price": round(random.uniform(1.0, 5.0), 2) #A random price between $1 and $5
    } for _ in range(n)]
    return parking_spots

def generate_reservations(users_list, parking_spots, reservation_count):
    reservations = []
    for _ in range(reservation_count):
        user_id = random.choice(users_list)
        random_spot = random.choice(parking_spots)
        reservation = {
            "id_user": user_id,
            "id_parking_lot": random_spot["parking_lot"], #Add this reservation to a random parking lot
            "id_parking_spot": random_spot["_id"], #Random simulated parking spot ID
            "timestamp": (datetime.now() - timedelta(hours = random.randint(1, 24))).strftime('%Y-%m-%dT%H:%M:%S'), #Random visit time
        }
        reservations.append(reservation)
    return reservations

#----------------------------------------------------------------------------------------------------
#   Post Data to API
#----------------------------------------------------------------------------------------------------

def post_data(url, data_list):
    for data in data_list:
        response = requests.post(url, json = data, headers={'Host': hostname}) #NOTE: added hostname due to traefik communication rule
        if response.status_code in [200, 201]:
            print(f'Successfully posted to {url}: {data}')
        else:
            print(f'Failed to post to {url}: {data}, Status Code: {response.status_code}')

#----------------------------------------------------------------------------------------------------
#   Get Data from API - used for ID reference cohesion
#----------------------------------------------------------------------------------------------------

def get_data(url):
    response = requests.get(url, headers={'Host': hostname}) #NOTE: added hostname due to traefik communication rule
    if response.status_code in [200, 201]:
            print(f'Successfully got data from {url}')
    else:
            print(f'Failed to get data from {url}, Status Code: {response.status_code}')

    return response.json()

#----------------------------------------------------------------------------------------------------
#   Script Execution
#----------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    

    

    

    #Generate and Post the fake data
    print("Registering Owners...")
    owners = generate_owners(2)
    post_data(f'{base_url_owner}/owners', owners)

    print("Adding Parking Lots...")
    parking_lot_owner_ids = get_data(f'{base_url_owner}/owners/ALL')
    parking_lots = generate_parking_lots(5, parking_lot_owner_ids)
    post_data(f'{base_url_owner}/parking_lots', parking_lots)

    print("Adding Parking Spots...")
    lot_ids_for_spots = get_data(f'{base_url_owner}/parking_lots/ALL')
    parking_spots = generate_parking_spots(100, lot_ids_for_spots)
    post_data(f'{base_url_owner}/parking_spots', parking_spots)

    print("Registering Users...")
    users = generate_users(10)
    post_data(f'{base_url_user}/register', users)

    users_ids = get_data(f'{base_url_owner}/users/ALL')
    spots_data = get_data(f'{base_url_owner}/parking_spots/ALL')
    print("Simulating Reservations...")
    reservations = generate_reservations(users_ids, spots_data, 20)

    for reservation in reservations:
        response = requests.post(f'{base_url_user}/reserve',
                                 json = reservation,
                                 headers = {'Host': hostname})
        if response.status_code in [200, 201]:
             print(f"Reservation successfull: {reservation}")
        else:
             print(f"Failed to create reservation: {reservation}, Status Code: {response.status_code}")
    


#Funkcija za randomizaciju podataka Redis-a (dolazak/odlazak) - delay od cca 5 min