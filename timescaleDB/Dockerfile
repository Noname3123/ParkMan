FROM timescale/timescaledb:latest-pg12


# Copy the initialization script to the container
COPY timescale-init.sh /docker-entrypoint-initdb.d/init-db.sh

# Ensure the script is executable
RUN chmod +x /docker-entrypoint-initdb.d/init-db.sh
