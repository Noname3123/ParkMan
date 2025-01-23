# Use the official Python image from the Docker Hub
FROM python:3.9-slim


#install cron
RUN apt-get update && apt-get install -y cron

# Set the working directory
WORKDIR /app


COPY requirements.txt .

# Install the Python dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . /app

# Copy the cron job file to the cron.d directory
COPY cronjob /etc/cron.d/cronjob

# Give execution rights on the cron job
RUN chmod 0644 /etc/cron.d/cronjob
RUN chmod a+x /app/etl_script.py

# Apply the cron job
RUN crontab /etc/cron.d/cronjob

# Create the log file to be able to run tail
RUN touch /var/log/cron.log



# Run the Python script
CMD ["bash","-c","cron && tail -f /var/log/cron.log"]
