
#!/bin/bash
set -e


# Ensure necessary environment variables are set
: "${POSTGRES_USER:?Environment variable POSTGRES_USER not set}"
: "${POSTGRES_DB:?Environment variable POSTGRES_DB not set}"
: "${POSTGRES_HOST:?Environment variable POSTGRES_HOST not set}"
: "${POSTGRES_PASSWORD:?Environment variable POSTGRES_PASSWORD not set}"



psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER"  --dbname "$POSTGRES_DB"<<-EOSQL
  CREATE DATABASE $POSTGRES_DB;
  GRANT ALL PRIVILEGES ON DATABASE $POSTGRES_DB TO $POSTGRES_USER;
  \c $POSTGRES_DB
  CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
  CREATE EXTENSION IF NOT EXISTS "pgcrypto";
  -- Create the parking_transactions table
  CREATE TABLE parking_transactions (
    transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parking_lot_id    TEXT             NOT NULL,
    parking_spot_id   INT             ,
    user_id           TEXT             NOT NULL,
    entry_timestamp   TIMESTAMPTZ     NOT NULL,
    exit_timestamp    TIMESTAMPTZ     NULL,
    checkout_price    NUMERIC(10, 2)  NULL
  );


 
  
  SELECT * from create_hypertable('parking_transactions', 'entry_timestamp');

  CREATE UNIQUE INDEX ON parking_transactions (transaction_id, entry_timestamp);
  
  CREATE INDEX ON parking_transactions (parking_lot_id); 
  CREATE INDEX ON parking_transactions (user_id);

  

  

EOSQL




