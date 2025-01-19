

#!/bin/bash
set -e

# Ensure necessary environment variables are set
: "${MONGO_DATABASE_NAME:?Environment variable MONGO_DATABASE_NAME not set}"
: "${MONGO_DATABASE_USER:?Environment variable MONGO_DATABASE_USER not set}"
: "${MONGO_DATABASE_PASS:?Environment variable MONGO_DATABASE_PASS not set}"
: "${MONGO_INITDB_ROOT_USERNAME:?Environment variable MONGO_INITDB_ROOT_USERNAME not set}"
: "${MONGO_INITDB_ROOT_PASSWORD:?Environment variable MONGO_INITDB_ROOT_PASSWORD not set}"
: "${MONGO_COLLECTION_NAMES:?Environment variable MONGO_COLLECTION_NAMES not set}"
: "${MONGO_DATABASE_EXTERNAL_USER:?Environment variable MONGO_DATABASE_EXTERNAL_USER not set}"
: "${MONGO_DATABASE_EXTERNAL_PASS:?Environment variable MONGO_DATABASE_EXTERNAL_PASS not set}"

echo "Starting MongoDB initialization script..."


# Switch to admin database to create the app user
mongosh admin <<EOF
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
#create user which can only read DB
var external_user = db.getSiblingDB('$MONGO_DATABASE_NAME').getUser('$MONGO_DATABASE_EXTERNAL_USER');
if (!external_user) {
    // Create application database and user
    db.getSiblingDB('$MONGO_DATABASE_NAME').createUser({
      user: "$MONGO_DATABASE_EXTERNAL_USER",
      pwd: "$MONGO_DATABASE_EXTERNAL_PASS",
      roles: [
        { role: "read", db: "$MONGO_DATABASE_NAME" }
      ]
    });
    print("Application user '$MONGO_DATABASE_EXTERNAL_USER' created successfully on '$MONGO_DATABASE_NAME'.");
} else {
    print("User '$MONGO_DATABASE_EXTERNAL_USER' already exists on '$MONGO_DATABASE_NAME'.");
}
EOF

# Initialize collections if they don't exist
mongosh "$MONGO_DATABASE_NAME" -u "$MONGO_DATABASE_USER" -p "$MONGO_DATABASE_PASS" --authenticationDatabase "$MONGO_DATABASE_NAME" <<EOF
var collections = $MONGO_COLLECTION_NAMES;
collections.forEach(function(collection) {
  if (db.getCollectionNames().indexOf(collection) === -1) {
  db.createCollection(collection);
  print("Collection '" + collection + "' created successfully in database '$MONGO_DATABASE_NAME'.");
  } else {
  print("Collection '" + collection + "' already exists in database '$MONGO_DATABASE_NAME'.");
  }
});
EOF

echo "MongoDB initialization complete."





echo "Begin sharding config for managerDB"

mongosh admin<< EOF
sh.enableSharding('$MONGO_DATABASE_NAME');
var db = db.getSiblingDB(dbName);
db.parking_lots.createIndex({ geolocation: "2dsphere" });
sh.shardCollection('{$MONGO_DATABASE_NAME}.parking_lots', { geolocation: "hashed" });
EOF

echo "MongoDB mongos sharding setup complete."


