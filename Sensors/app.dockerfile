
FROM python:3.12

#Set working directory in the container
WORKDIR /app

#Copy requirements.txt
COPY requirements.txt .

#Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

#Copy the application code into the container at /app
COPY ./source_code/ ./source_code/

#Expose port 80 inside the container
EXPOSE 80

#Run the app
CMD ["python", "./source_code/API_senzori/app.py"]