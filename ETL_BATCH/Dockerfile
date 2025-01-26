# Use the official Python image from the Docker Hub
FROM python:3.9-slim




# Set the working directory
WORKDIR /app


COPY requirements.txt .

# Install the Python dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . /app



# Give execution rights on the cron job
RUN chmod a+x /app/etl_script.py




# Run the Python script
CMD ["bash","-c","python /app/etl_script.py"]
