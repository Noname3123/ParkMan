#!/bin/sh 
echo 'Waiting for MinIO...';
until (/usr/bin/mc config host add localminio http://"${MINIO_ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}") do sleep 1; done;
echo 'MinIO ready, setting up buckets and policies...';
/usr/bin/mc mb localminio/camera-images || true;
/usr/bin/mc mb localminio/local-storage-raw || true;
/usr/bin/mc anonymous set public localminio/camera-images; # TODO:  Example: make camera images public if needed, check if needed
echo 'Setting 30 day expiry for local-storage-raw...';
/usr/bin/mc ilm rule import localminio/local-storage-raw < /config/lifecycle.json;
echo 'MinIO setup complete.';
