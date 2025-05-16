FROM python:3.12-slim
WORKDIR /app
COPY app.py /app/
RUN pip install --no-cache-dir flask redis boto3 requests
CMD ["python", "app.py"]