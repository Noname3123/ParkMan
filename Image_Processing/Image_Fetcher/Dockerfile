FROM python:3.10-slim

WORKDIR /app

RUN pip install --no-cache-dir boto3 kafka-python pymongo python-dotenv redis

COPY app.py .

CMD ["python", "-u" ,"app.py"]