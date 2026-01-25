import requests
import json

# Configuration
HOSTNAME = 'parkman.localhost'
# Traefik routes from 8001 to 80. Since this runs outside containers, use localhost:8001
BASE_URL_API = 'http://localhost:8001/api' 

HEADERS = {'Host': HOSTNAME, 'Content-Type': 'application/json'}

def create_specific_data():
    # 1. Create Specific Owner
    print("--- Creating Specific Owner ---")
    owner_payload = {
        "name": "Ivan",
        "surname": "Horvat"
    }
    
    response = requests.post(f"{BASE_URL_API}/owners", json=owner_payload, headers=HEADERS)
    
    if response.status_code != 201:
        print(f"Error creating owner: {response.text}")
        return
    
    response_data = response.json()
    owner_id = response_data.get("id")
    
    if not owner_id:
        print("Error: Owner created, but ID was not returned. Ensure routes.py is updated.")
        return

    print(f"Owner created with ID: {owner_id}")

    # 2. Create Specific Parking Lot
    print("\n--- Creating Specific Parking Lot ---")
    lot_payload = {
        "name": "Zagreb City Center Garage",
        "geolocation": [45.8150, 15.9819], # Example coordinates
        "owner_id": owner_id
    }
    
    response = requests.post(f"{BASE_URL_API}/parking_lots", json=lot_payload, headers=HEADERS)
    
    if response.status_code != 201:
        print(f"Error creating parking lot: {response.text}")
        return
        
    lot_data = response.json()
    # The API returns the ID inside the 'details' object for parking lots
    lot_id = lot_data.get("details", {}).get("id")
    
    if not lot_id:
        print("Error: Parking lot ID not found in response.")
        return
        
    print(f"Parking lot created with ID: {lot_id}")

    # 3. Create 30 Parking Spots
    print("\n--- Creating 30 Parking Spots ---")
    spot_price = 2.50
    
    for i in range(30):
        spot_payload = {
            "parking_lot": lot_id,
            "spot_price": spot_price
        }
        
        response = requests.post(f"{BASE_URL_API}/parking_spots", json=spot_payload, headers=HEADERS)
        
        if response.status_code == 201:
            print(f"Spot {i+1}/30 created.")
        else:
            print(f"Failed to create spot {i+1}: {response.text}")
            
    print("\n--- Specific data generation complete ---")

if __name__ == "__main__":
    create_specific_data()
