import os
from dotenv import load_dotenv
from pymongo import MongoClient
from psycopg2 import connect 
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from bson import ObjectId
import clickhouse_connect
import redis
from prometheus_client import *
import schedule
import time as tm 


##Prometheus metrics

ETL_EXECUTION_TIME = Summary('etl_execution_time', 'Time spent processing an ETL run')
LAST_EXECUTION_TIME = Gauge('last_etl_execution', 'Timestamp of the last ETL execution')
ETL_RECORDS_PROCESSED = Counter('etl_records_processed', 'Total number of records processed by the ETL')
ETL_THROUGHPUT = Gauge('etl_throughput', 'Records processed per second')



##


def get_data_from_redis():
    keys=redis_conn.keys(REDIS_DATA_KEY_PATTERN)
    
    #get all hashmaps from keys -> keys are of struct parking_lot:mongoDBDocID
    parking_lots_data={ObjectId(key.split(":")[-1]): redis_conn.hgetall(key) for key in keys}
    
    

    filtered_ids = {
            'parking_lot_ids': list(set(ObjectId(entry) for entry in parking_lots_data.keys()))
    }


    

    return parking_lots_data, filtered_ids

def get_filtered_data_from_mongo(filtered_ids):

    owner_data=db_external_manager.owners
    parking_lot_data=db_external_manager.parking_lots

    parking_lot_ids = filtered_ids['parking_lot_ids']

    parking_lots = {parking_lot['_id']: (parking_lot['name'], len(parking_lot['parking_spaces'])) for parking_lot in parking_lot_data.find({'_id': {'$in': parking_lot_ids}})}

    owners = {owner['_id']: (owner['name'] + " " + owner['surname'], owner['parking_lots']) for owner in owner_data.find({'parking_lots': {'$in': parking_lot_ids}})}

    return parking_lots, owners


def find_appropriate_owner(owner,parking_lot_id):
    
    for (key,val) in owner.items():
        if ObjectId(parking_lot_id) in val[1]:
            return (key,val[0])

def merge_data(parking_lots_data, parking_lots, owner,input_time):

    expanded_data = []
    for key in parking_lots_data:
        parking_lot_id=key
        owner_id, full_name=find_appropriate_owner(owner, parking_lot_id)
        expanded_entry={
            'timestamp': input_time,
            'owner_id': owner_id,
            'owner_full_name': full_name,
            'parking_lot_id': parking_lot_id,
            'parking_lot_name': parking_lots.get(parking_lot_id)[0],
            'parking_spot_number': parking_lots.get(parking_lot_id)[1],
            'car_count':parking_lots_data.get(parking_lot_id).get("car_num")
        }

        expanded_data.append(expanded_entry)
    return expanded_data

    
def import_data_into_click_house(data):
    def chunk_data(data, chunk_size=100):
        for i in range(0, len(data), chunk_size):
            yield data[i:i + chunk_size]
            
    for chunk in chunk_data(data):
        query = """
        INSERT INTO parking_db.parking_usage (timestamp, owner_id, owner_full_name, parking_lot_id, parking_lot_name, parking_spot_number, car_count)
        VALUES
        """
        values = ', '.join(f"('{entry['timestamp']}','{entry['owner_id']}', '{entry['owner_full_name']}', '{entry['parking_lot_id']}', '{entry['parking_lot_name']}', '{entry['parking_spot_number']}', '{entry['car_count']}'  )" for entry in chunk)
        query += values
        client.command(query)




# =========================
# Simulation Helper
# =========================
SIMULATION_MODE = os.getenv("SIMULATION_MODE", "false").lower() == "true"
SIM_START_REAL = tm.time()
SIM_START_DT = datetime.now()

def get_current_time():
    if SIMULATION_MODE:
        # 1 real second = 1800 simulated seconds (30 mins)
        # 2 real seconds = 3600 simulated seconds (1 hour)
        elapsed = tm.time() - SIM_START_REAL
        return SIM_START_DT + timedelta(seconds=elapsed * 1800)
    return datetime.now()

def exec_etl():

    start=tm.time()

    ###DO ETL
    input_time=get_current_time()

    parking_lots_data, filtered_ids= get_data_from_redis()
    parking_lots,owner=get_filtered_data_from_mongo(filtered_ids)

    merged=merge_data(parking_lots_data,parking_lots,owner, input_time)


    import_data_into_click_house(merged)
    ###

    end=tm.time()

    #Measure how long it executed
    ETL_EXECUTION_TIME.observe(end-start)

    # Update throughput
    ETL_THROUGHPUT.set(len(merged) / (end-start))

    #increment counter
    ETL_RECORDS_PROCESSED.inc(len(merged))

    LAST_EXECUTION_TIME.set_to_current_time()

    print(f"Imported REDIS data into clickhouse - timestamp {input_time}")



if __name__ == "__main__":
    

    ### load env
    load_dotenv()


    #### MongoDB config

    MONGO_EXTERNAL_MANAGER=os.getenv("MONGO_MANAGER_DATABASE_R_ONLY_URI", "mongodb://external:external_pass@localhost:27016/ParkMan_manager_db")
    external_client_managerDB=MongoClient(MONGO_EXTERNAL_MANAGER)
    db_external_manager=external_client_managerDB.get_database()

    ### Redis DB connection
    REDIS_HOST=os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT=int(os.getenv('REDIS_PORT', 6379))
    redis_conn=redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)



    ###clickhouse target connect
    CLICKHOUSE_PORT=os.getenv("CLICKHOUSE_PORT", 8123)
    CLICKHOUSE_HOST=os.getenv("CLICKHOUSE_HOST", "localhost")
    CLICKHOUSE_USER=os.getenv("CLICKHOUSE_USER", "parkman_user")
    CLICKHOUSE_PASS=os.getenv("CLICKHOUSE_PASS", "parkman_user_pass")

    client = clickhouse_connect.get_client(host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT, user=CLICKHOUSE_USER, password=CLICKHOUSE_PASS)

    ###get redis search key pattern
    REDIS_DATA_KEY_PATTERN= os.getenv("REDIS_DATA_KEY_PATTERN",'parking_lot:*')


    
    ##Expose metrics in server on port 9395
    
    start_http_server(9395)


    ## define schedule (every 1 mins)
    schedule.every(3).seconds.do(exec_etl)

    #exec job in schedule
    while True:
        schedule.run_pending()
        tm.sleep(1)
