
#!/bin/bash
set -e


# Ensure necessary environment variables are set
: "${POSTGRES_USER:?Environment variable POSTGRES_USER not set}"
: "${POSTGRES_DB:?Environment variable POSTGRES_DB not set}"
: "${POSTGRES_HOST:?Environment variable POSTGRES_HOST not set}"



psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER"  --dbname "$POSTGRES_DB"<<-EOSQL
  CREATE DATABASE $POSTGRES_DB;
  GRANT ALL PRIVILEGES ON DATABASE $POSTGRES_DB TO $POSTGRES_USER;
  \c $POSTGRES_DB
  CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
  -- Create the ParkingTransactions table
  CREATE TABLE ParkingTransactions (
    parking_lot_id    INT             NOT NULL,
    parking_spot_id   INT             NOT NULL,
    user_id           INT             NOT NULL,
    entry_timestamp   TIMESTAMPTZ     NOT NULL,
    exit_timestamp    TIMESTAMPTZ     NULL,
    checkout_price    NUMERIC(10, 2)  NULL
  );
EOSQL




