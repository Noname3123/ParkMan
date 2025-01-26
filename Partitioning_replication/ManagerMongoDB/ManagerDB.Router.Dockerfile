
FROM mongo:latest

RUN mkdir /scripts

COPY ./Partitioning_replication/ManagerMongoDB/sharded-mongoDB-init.sh /scripts

RUN chmod +x /scripts/sharded-mongoDB-init.sh
