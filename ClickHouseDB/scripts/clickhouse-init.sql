





CREATE DATABASE IF NOT EXISTS parking_db;
CREATE TABLE IF NOT EXISTS parking_db.parking_analytics  (
    owner_id String,            -- ID of parking lot owner (from MongoDB)
    owner_full_name String,     -- Name + surname of owner (MongoDB)
    parking_lot_id String,      -- ID of parking lot (from TimescaleDB)
    parking_lot_name String,    -- Name of parking lot (MongoDB)
    parking_spot_number Int32,  -- Number of parking spots for the parking lot (from MongoDB)
    user_id String,             -- ID of user who parked (from TimescaleDB)
    user_full_name String,             -- Name + surname of user (MongoDB)
    entry_timestamp DateTime,   -- When user entered parking lot (from TimescaleDB)
    leaving_timestamp DateTime, -- When user left parking lot (from TimescaleDB)
    checkout_price Float64      -- How much user has to pay for parking (from TimescaleDB)
) 
ENGINE = MergeTree()
PARTITION BY (owner_id, toYYYYMM(entry_timestamp))  -- Composite partition by owner_id and year-month of entry_timestamp
ORDER BY (owner_id, owner_name, parking_lot_id, parking_lot_name, entry_timestamp, user_id, user_name);  -- Order by owner_id and name, parking_lot_id and name, entry_timestamp, and user_id

CREATE USER parkman_user IDENTIFIED BY 'parkman_user_pass';
GRANT ALTER, SELECT ON parking_db.parking_analytics TO parkman_user; 
GRANT ALTER ON parking_db TO parkman_user; 


