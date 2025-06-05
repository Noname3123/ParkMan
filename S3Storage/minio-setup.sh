#!/bin/sh 
echo 'Waiting for MinIO...';
until (/usr/bin/mc config host add localminio http://"${MINIO_ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}") do sleep 1; done;
echo 'MinIO ready, setting up buckets and policies...';
/usr/bin/mc mb localminio/camera-images || true;
/usr/bin/mc anonymous set public localminio/camera-images; # TODO:  Example: make camera images public if needed, check if needed
/usr/bin/mc mb localminio/edited-images || true;
/usr/bin/mc anonymous set public localminio/edited-images; # TODO:  Example: make camera images public if needed, check if needed


echo "Creating user ${APP_MINIO_ACCESS_KEY} for API_voditelj..."
/usr/bin/mc admin user add localminio "${APP_MINIO_ACCESS_KEY}" "${APP_MINIO_SECRET_KEY}" || echo "User ${APP_MINIO_ACCESS_KEY} already exists or failed to create."
echo "Creating policy apiVoditeljPolicy..."
/usr/bin/mc admin policy create localminio apiVoditeljPolicy /config/api_voditelj_policy.json || echo "Policy apiVoditeljPolicy already exists or failed to create."
echo "Attaching policy apiVoditeljPolicy to user ${APP_MINIO_ACCESS_KEY}..."
/usr/bin/mc admin policy attach localminio apiVoditeljPolicy --user "${APP_MINIO_ACCESS_KEY}" || echo "Failed to attach policy apiVoditeljPolicy to user ${APP_MINIO_ACCESS_KEY} or already attached."
echo 'MinIO setup complete.';
