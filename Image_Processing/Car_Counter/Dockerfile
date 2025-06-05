FROM python:3.12-slim
WORKDIR /app
COPY app.py /app/
RUN pip install --no-cache-dir flask redis boto3 requests python-dotenv
EXPOSE 5001
CMD ["python", "-u" ,"app.py"]