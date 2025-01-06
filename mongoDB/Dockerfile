
FROM mongo:6.0

# Copy the initialization script into the image
COPY mongo-init.sh /docker-entrypoint-initdb.d/mongo-init.sh

# Ensure the script has execute permissions
RUN chmod +x /docker-entrypoint-initdb.d/mongo-init.sh
