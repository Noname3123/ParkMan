
#!/bin/bash
set -e

# Ensure necessary environment variables are set
: "${MONGO_DATABASE_NAME:?Environment variable MONGO_DATABASE_NAME not set}"
: "${MONGO_DATABASE_USER:?Environment variable MONGO_DATABASE_USER not set}"
: "${MONGO_DATABASE_PASS:?Environment variable MONGO_DATABASE_PASS not set}"
: "${MONGO_INITDB_ROOT_USERNAME:?Environment variable MONGO_INITDB_ROOT_USERNAME not set}"
: "${MONGO_INITDB_ROOT_PASSWORD:?Environment variable MONGO_INITDB_ROOT_PASSWORD not set}"

echo "Starting MongoDB initialization script..."

# Switch to admin database to create the app user
mongosh admin -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase "admin" <<EOF
var user = db.getSiblingDB('$MONGO_DATABASE_NAME').getUser('$MONGO_DATABASE_USER');
if (!user) {
    // Create application database and user
    db.getSiblingDB('$MONGO_DATABASE_NAME').createUser({
      user: "$MONGO_DATABASE_USER",
      pwd: "$MONGO_DATABASE_PASS",
      roles: [
        { role: "readWrite", db: "$MONGO_DATABASE_NAME" }
      ]
    });
    print("Application user '$MONGO_DATABASE_USER' created successfully on '$MONGO_DATABASE_NAME'.");
} else {
    print("User '$MONGO_DATABASE_USER' already exists on '$MONGO_DATABASE_NAME'.");
}
EOF

echo "MongoDB initialization complete."

