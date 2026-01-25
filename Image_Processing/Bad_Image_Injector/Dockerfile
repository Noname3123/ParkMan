FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# CHANGE: ako želiš da container u sebi ima bad sample:
 COPY ../bad_samples /app/bad_samples

CMD ["python", "app.py", "--mode", "s3", "--bad-image", "/app/bad_samples/empty_parking.jpg", "--count", "20"]
