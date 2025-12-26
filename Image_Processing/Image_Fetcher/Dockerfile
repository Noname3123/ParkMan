FROM python:3.10-slim

WORKDIR /app

RUN pip install --no-cache-dir boto3 confluent_kafka pymongo python-dotenv redis

COPY app.py .

CMD ["python", "-u" ,"app.py"]