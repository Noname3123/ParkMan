FROM python:3.12-slim
WORKDIR /app
COPY app.py /app/
RUN pip install --no-cache-dir confluent-kafka boto3 requests python-dotenv pillow
ENTRYPOINT ["python", "-u" ,"app.py"]