#!/bin/bash
set -e

RETRIES=5
SLEEP=5

MANAGER_HOST="${MANAGER_HOST:-manager_app}"
MANAGER_PORT="${MANAGER_PORT:-80}"
SENSOR_HOST="${SENSOR_HOST:-sensor_app}"
SENSOR_PORT="${SENSOR_PORT:-80}"

echo "===> Checking Manager API and Sensor API availability before starting Redis..."

#Function to test if and HTTP GET on Manager and Sensor API is up
check_api_up() {
    local host="$1"
    local port="$2"

    curl -s --max-time 2 "http://$host:$port" > /dev/null
}

#Retry loop for Manager API
for i in $(seq 1 $RETRIES); do
    if check_api_up "$MANAGER_HOST" "$MANAGER_PORT"; then
        echo "Manager API is up!"
        break
    else
        echo "Manager API is not up yet... retry $i/$RETRIES"
        sleep $SLEEP
    fi
    #If Manager API was never reached
    if [ $i -eq $RETRIES ]; then
        echo "Manager API not available after $RETRIES tries, aborting."
        exit 1
    fi
done

#Retry loop for Sensor API
for i in $(seq 1 $RETRIES); do
    if check_api_up "$SENSOR_HOST" "$SENSOR_PORT"; then
        echo "Sensor API is up!"
        break
    else
        echo "Sensor API is not up yet... retry $i/$RETRIES"
        sleep $SLEEP
    fi
    #If Sensor API was never reached
    if [ $i -eq $RETRIES ]; then
        echo "Sensor API not available after $RETRIES tries, aborting."
        exit 1
    fi
done

echo "===> Both Manager & Sensor appear up. Now launching Redis..."

exec "$@"

echo "===> Done launching. Now running redis_init to fill the data..."

source /app/venv/bin/activate

sleep 15

python3 ./redis_init.py



