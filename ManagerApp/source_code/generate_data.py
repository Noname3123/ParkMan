from faker import Faker
import requests
from datetime import datetime, timedelta
import random

fake = Faker()

hostname='parkman.localhost' #NOTE: added hostname due to traefik communication rule Host(parkman.localhost - which is the name of nginx service in docker-compose)

base_url_user = 'http://0.0.0.0:80/user'
base_url_owner = 'http://0.0.0.0:80/api'

#----------------------------------------------------------------------------------------------------
#   Data Generation
#----------------------------------------------------------------------------------------------------

def generate_users(n):
    users = [{
        "username": fake.user_name(),
        "password": fake.password(),
        "car_registration": [fake.license_plate() for _ in range(random.randint(1, 3))]
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
        "geolocation": [fake.latitude(), fake.longitude()],
        "owner_id": random.choice(owners).get("_id") #Add this parking lot to a random owner
    } for _ in range(n)]
    return parking_lots

def generate_parking_spots(n, parking_lots):
    parking_spots = [{
        "parking_lot": random.choice(parking_lots).get("_id"), #Add this parking spot to a random parking lot
        "spot_price": round(random.uniform(1.0, 5.0), 2) #A random price between $1 and $5
    } for _ in range(n)]
    return parking_spots

def generate_reservations(users, parking_lots):
    reservations = [{
        "id_user": random.choice(users).get("_id"), #Add this reservation to a random user
        "id_parking_lot": random.choice(parking_lots).get("_id"), #Add this reservation to a random parking lot
        "timestamp": (datetime.now() - timedelta(hours = random.randint(1, 24))).strftime('%Y-%m-%dT%H:%M:%S'), #Random visit time
        "id_parking_spot": random.randint(1, 100) #Random simulated parking spot ID
    } for _ in range(len(users))]
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
#   Script Execution
#----------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    #Generate fake data
    users = generate_users(10)
    owners = generate_owners(2)
    parking_lots = generate_parking_lots(5, owners)
    parking_spots = generate_parking_spots(100, parking_lots)
    reservations = generate_reservations(users, parking_lots)

    #Post the fake data
    print("Registering Owners...")
    post_data(f'{base_url_owner}/owners', owners)

    print("Adding Parking Lots...")
    post_data(f'{base_url_owner}/parking_lots', parking_lots)

    print("Adding Parking Spots...")
    post_data(f'{base_url_owner}/parking_spots', parking_spots)

    print("Registering Users...")
    post_data(f'{base_url_user}/register', users)

    print("Simulating Reservations...")
    for reservation in reservations:
        response = requests.post(f'{base_url_user}/reserve', json = reservation, headers = {'Host': hostname})
        if response.status_code in [200, 201]:
            print(f"Reservation successful: {reservation}")
        else:
            print(f"Failed to create reservation: {reservation}, Status Code: {response.status_code}")