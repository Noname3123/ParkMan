import os
import time
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError, NoBrokersAvailable

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092') # Internal Docker address
TOPIC_NAME = os.environ.get('TOPIC_NAME', 'cctv-image-events')
NUM_PARTITIONS = int(os.environ.get('NUM_PARTITIONS', 3))
REPLICATION_FACTOR = int(os.environ.get('REPLICATION_FACTOR', 1))

# --- Wait for Kafka ---
def wait_for_kafka(bootstrap_servers, retries=10, delay=5):
    print(f"Waiting for Kafka at {bootstrap_servers}...")
    for i in range(retries):
        try:
            admin_client = KafkaAdminClient(bootstrap_servers=bootstrap_servers)
            # Trying to list topics is a good way to check if Kafka is truly ready
            admin_client.list_topics()
            print("Kafka is available.")
            return admin_client
        except NoBrokersAvailable:
            print(f"Kafka not available yet (attempt {i+1}/{retries}). Retrying in {delay}s...")
            time.sleep(delay)
        except Exception as e:
            print(f"An unexpected error occurred while waiting for Kafka: {e}")
            # Might indicate a different startup issue
            return None # Exit if wait fails for other reasons

    print("Kafka did not become available within the timeout.")
    return None


# --- Create Topic ---
if __name__ == "__main__":
    admin_client = None
    try:
        # Use the internal Docker network address for bootstrap servers
        admin_client = wait_for_kafka(KAFKA_BOOTSTRAP_SERVERS.split(','))

        if admin_client:
            topic_list = [
                NewTopic(
                    name=TOPIC_NAME,
                    num_partitions=NUM_PARTITIONS,
                    replication_factor=REPLICATION_FACTOR
                )
            ]
            print(f"Attempting to create topic: {TOPIC_NAME} with {NUM_PARTITIONS} partitions and replication factor {REPLICATION_FACTOR}")

            try:
                admin_client.create_topics(
                    new_topics=topic_list,
                    validate_only=False
                )
                print(f"Topic '{TOPIC_NAME}' created successfully (or already exists).")
            except TopicAlreadyExistsError:
                print(f"Topic '{TOPIC_NAME}' already exists.")
            except Exception as e:
                print(f"Error creating topic '{TOPIC_NAME}': {e}")
                exit(1) # Exit with error code on failure

    except Exception as e:
        print(f"An error occurred during setup: {e}")
        exit(1)
    finally:
        if admin_client:
            admin_client.close()
            print("Admin client closed.")
