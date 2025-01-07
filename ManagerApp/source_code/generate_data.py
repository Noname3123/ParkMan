from faker import Faker
import requests

fake = Faker()

hostname='parkman.localhost' #NOTE: added hostname due to traefik communication rule Host(parkman.localhost - which is the name of nginx service in docker-compose)

def generate_users(n):
    users = [{
        "username": fake.user_name(),
        "password": fake.password(),
        "email": fake.email(),
        "name": fake.name()
    } for _ in range(n)]
    return users

def generate_parks(n):
    parks = [{
        "name": fake.company(),
        "location": fake.address(),
        "spots": fake.random_int(min = 20, max = 100),
        "price_per_spot": fake.random_int(min = 1, max = 3)
    } for _ in range(n)]
    return parks

def post_data(url, data_list):
    for data in data_list:
        response = requests.post(url, json = data, headers={'Host': hostname}) #NOTE: added hostname due to traefik communication rule
        if response.status_code == 201:
            print(f'Successfully posted to {url}: {data}')
        else:
            print(f'Failed to post to {url}: {data}, Status Code: {response.status_code}')

if __name__ == "__main__":
    base_url_user = 'http://localhost:8001/user' #NOTE: have to change this to the correct port of server
    base_url_leader = 'http://localhost:8001/api'

    users = generate_users(10)
    parks = generate_parks(10)

    post_data(f'{base_url_user}/register', users)
    post_data(f'{base_url_leader}/parks', parks)