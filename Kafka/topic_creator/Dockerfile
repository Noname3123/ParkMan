FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt

COPY topic_creator.py .

CMD ["python", "topic_creator.py"]
