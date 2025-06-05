-- This script should be run after clickhouse-init.sql as it assumes parking_db and parkman_user exist.

CREATE TABLE IF NOT EXISTS parking_db.parking_usage (
    timestamp DateTime,         -- Time when entry "sampled" (from RedisDB)
    owner_id String,            -- ID of parking lot owner (originates from MongoDB)
    owner_full_name String,     -- Name + surname of owner ( originates from MongoDB)
    parking_lot_id String,      -- ID of parking lot ( originates from TimescaleDB/MongoDB)
    parking_lot_name String,    -- Name of parking lot ( originates from MongoDB)
    parking_spot_number Int32,  -- Number of parking spots for the parking lot (from RedisDB, originates from MongoDB)
    car_count Int32             -- Number of counted cars on parking (from RedisDB)
)
ENGINE = MergeTree()
PARTITION BY (owner_id, toYYYYMM(timestamp)) -- Composite partition by owner_id and year-month of timestamp
ORDER BY (owner_id, parking_lot_id, timestamp); -- Order by owner, parking lot, and then by time

GRANT ALTER, SELECT, INSERT ON parking_db.parking_usage TO parkman_user;