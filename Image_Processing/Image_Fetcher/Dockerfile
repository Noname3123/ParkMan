FROM python:3.10-slim

# Install system dependencies required for building confluent-kafka
RUN apt-get update && apt-get install -y \
    gcc \
    librdkafka-dev \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /app

RUN pip install --no-cache-dir boto3 confluent-kafka pymongo python-dotenv redis

COPY app.py .

CMD ["python", "-u" ,"app.py"]