#!/bin/sh
set -e # Exit immediately if a command exits with a non-zero status.

SQL_SCRIPT_PATH="/tmp/clickhouse-init-parking-usage.sql" # Path inside the admin container
CLICKHOUSE_HOST="clickhouse" # Service name of your ClickHouse server
CLICKHOUSE_USER="default"    # User to connect as (default usually has admin rights)
CLICKHOUSE_PASSWORD=""       # Password for the user (leave empty if default user has no password)
                             # Adjust per users.xml (configures a password for the 'default' user).

ATTEMPTS=0
MAX_ATTEMPTS=12 # Try for 1 minute (12 attempts * 5 seconds = 60 seconds)

echo "Admin Container: Waiting for ClickHouse server ($CLICKHOUSE_HOST) to be ready..."

# Loop until ClickHouse is responsive or max attempts are reached
until [ "$ATTEMPTS" -ge "$MAX_ATTEMPTS" ] || clickhouse-client -h "$CLICKHOUSE_HOST" --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query 'SELECT 1' >/dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS+1))
  echo "Admin Container: ClickHouse not ready (attempt $ATTEMPTS/$MAX_ATTEMPTS), retrying in 5s..."
  sleep 5
done

if [ "$ATTEMPTS" -ge "$MAX_ATTEMPTS" ]; then
  echo "Admin Container: Failed to connect to ClickHouse server after $MAX_ATTEMPTS attempts. Exiting."
  exit 1
fi

echo "Admin Container: ClickHouse server is ready. Executing SQL script: $SQL_SCRIPT_PATH"
clickhouse-client -h "$CLICKHOUSE_HOST" --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --multiquery < "$SQL_SCRIPT_PATH"

echo "Admin Container: SQL script executed successfully. Container will now exit."
exit 0
