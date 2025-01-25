import os
from dotenv import load_dotenv
from pymongo import MongoClient
from psycopg2 import connect 
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from bson import ObjectId
import clickhouse_connect
from prometheus_client import *
import schedule
import time as tm 




##Prometheus metrics

ETL_EXECUTION_TIME = Summary('etl_execution_time', 'Time spent processing an ETL run')
LAST_EXECUTION_TIME = Gauge('last_etl_execution', 'Timestamp of the last ETL execution')
ETL_RECORDS_PROCESSED = Counter('etl_records_processed', 'Total number of records processed by the ETL')
ETL_THROUGHPUT = Gauge('etl_throughput', 'Records processed per second')



##




def get_data_from_timescale(begin_range, end_range):
    ##get all data from timescale fitting range:
    query_timescale = """
        SELECT * FROM parking_transactions
        WHERE entry_timestamp >= %s AND ( exit_timestamp <= %s OR exit_timestamp IS NULL );
    """
    timescale_cursor.execute(query_timescale, (begin_range, end_range))
    data_timescale = timescale_cursor.fetchall()

    filtered_ids = {
            'parking_lot_ids': list(set(ObjectId(entry['parking_lot_id']) for entry in data_timescale)),
            'user_ids': list(set(ObjectId(entry['user_id']) for entry in data_timescale))
    }


    

    return data_timescale, filtered_ids

def get_filtered_data_from_mongo(filtered_ids):
    user_data=db_external_user.users

    owner_data=db_external_manager.owners
    parking_lot_data=db_external_manager.parking_lots
    parking_space_data=db_external_manager.parking_spaces

    parking_lot_ids = filtered_ids['parking_lot_ids']
    user_ids = filtered_ids['user_ids']

    parking_lots = {parking_lot['_id']: (parking_lot['name'], len(parking_lot['parking_spaces'])) for parking_lot in parking_lot_data.find({'_id': {'$in': parking_lot_ids}})}
    users = {user['_id']: user['name']+" " + user['surname'] for user in user_data.find({'_id':  {'$in': user_ids}}) }

    owners = {owner['_id']: (owner['name'] + " " + owner['surname'], owner['parking_lots']) for owner in owner_data.find({'parking_lots': {'$in': parking_lot_ids}})}

    return parking_lots, users, owners


def find_appropriate_owner(owner,parking_lot_id):
    
    for (key,val) in owner.items():
        if ObjectId(parking_lot_id) in val[1]:
            return (key,val[0])

def merge_data(data_timescale, parking_lots, users, owner):

    expanded_data = []
    for entry in data_timescale:
        parking_lot_id=(entry['parking_lot_id'])
        user_id=entry['user_id']
        owner_id, full_name=find_appropriate_owner(owner, parking_lot_id)
        expanded_entry={
            'owner_id': owner_id,
            'owner_full_name': full_name,
            'parking_lot_id': parking_lot_id,
            'parking_lot_name': parking_lots.get(ObjectId(parking_lot_id))[0],
            'parking_spot_number': parking_lots.get(ObjectId(parking_lot_id))[1],
            'user_id': user_id,
            'user_full_name': users.get(ObjectId(user_id)),
            'entry_timestamp': entry['entry_timestamp'],
            'leaving_timestamp': entry['exit_timestamp'],
            'checkout_price': entry['checkout_price']
        }

        expanded_data.append(expanded_entry)
    return expanded_data

    
def import_data_into_click_house(data):
    query = """
    INSERT INTO parking_db.parking_analytics (owner_id, owner_full_name, parking_lot_id, parking_lot_name, parking_spot_number, user_id, user_full_name, entry_timestamp, leaving_timestamp, checkout_price)
    VALUES
    """
    values = ', '.join(f"('{entry['owner_id']}', '{entry['owner_full_name']}', '{entry['parking_lot_id']}', '{entry['parking_lot_name']}', '{entry['parking_spot_number']}', '{entry['user_id']}', '{entry['user_full_name']}', '{entry['entry_timestamp']}', '{entry['leaving_timestamp']}','{entry['checkout_price']}'  )" for entry in data)
    query += values
    client.command(query)



def exec_etl():

    start=tm.time()
    
    ## Get time range
    end_range= datetime.now()

    begin_range = end_range - timedelta(hours=24)
    ##

    ##Do ETL
    data_timescale, filtered_ids= get_data_from_timescale(begin_range, end_range)
    parking_lots,users,owner=get_filtered_data_from_mongo(filtered_ids)

    merged=merge_data(data_timescale,parking_lots,users,owner)
    

    import_data_into_click_house(merged)
    ##

    end=tm.time()


    #Measure how long it executed
    ETL_EXECUTION_TIME.observe(end-start)

    # Update throughput
    ETL_THROUGHPUT.set(len(merged) / (end-start))

    #increment counter
    ETL_RECORDS_PROCESSED.inc(len(merged))

    LAST_EXECUTION_TIME.set_to_current_time()


if __name__=='__main__':

    ### load env
    load_dotenv()


    #### MongoDB config

    MONGO_EXTERAL_USER_URI = os.getenv("MONGO_USER_DATABASE_R_ONLY_URI", "mongodb://external:external_pass@localhost:27017/ParkMan_user_db")
    client_external_user_db = MongoClient(MONGO_EXTERAL_USER_URI)
    db_external_user = client_external_user_db.get_database()

    MONGO_EXTERNAL_MANAGER=os.getenv("MONGO_MANAGER_DATABASE_R_ONLY_URI", "mongodb://external:external_pass@localhost:27016/ParkMan_manager_db")
    external_client_managerDB=MongoClient(MONGO_EXTERNAL_MANAGER)
    db_external_manager=external_client_managerDB.get_database()

    ### Timescale DB connection
    TIMESCALE_DB_URI=os.getenv("TIMESCALE_DB_DATABASE_URI", "postgresql://postgres_user:postgres_pass@localhost:5432/ParkingTransactionsDB")
    timescale_conn=connect(TIMESCALE_DB_URI)
    timescale_cursor=timescale_conn.cursor(cursor_factory=RealDictCursor)



    ###clickhouse target connect
    CLICKHOUSE_PORT=os.getenv("CLICKHOUSE_PORT", 8123)
    CLICKHOUSE_HOST=os.getenv("CLICKHOUSE_HOST", "localhost")
    CLICKHOUSE_USER=os.getenv("CLICKHOUSE_USER", "parkman_user")
    CLICKHOUSE_PASS=os.getenv("CLICKHOUSE_PASS", "parkman_user_pass")

    client = clickhouse_connect.get_client(host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT, user=CLICKHOUSE_USER, password=CLICKHOUSE_PASS)



    ##Expose metrics in server on port 9395
    
    start_http_server(9395)


    ## define schedule (every 3 mins)
    schedule.every(3).minutes.do(exec_etl)

    #exec job in schedule
    while True:
        schedule.run_pending()
        tm.sleep(1)


    #print(f"Imported data into clickhouse range {begin_range}, {end_range}")
