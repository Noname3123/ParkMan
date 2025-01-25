# Start from the official Redis image
FROM redis:latest

# Install needed packages: python3, pip, venv, plus dos2unix if on Windows
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv dos2unix curl \
    && apt-get clean

# We'll do all our work in /app
WORKDIR /app

COPY requirements.txt .
COPY entrypoint.sh .
COPY redis_init.py .

RUN dos2unix ./entrypoint.sh

# Make the script executable
RUN chmod +x ./entrypoint.sh

# Create a Python virtual environment
RUN python3 -m venv /app/venv \
 && /app/venv/bin/pip install --upgrade pip \
 && /app/venv/bin/pip install --no-cache-dir -r requirements.txt

# So we can run Python inside the container easily
ENV PATH="/app/venv/bin:$PATH"

# Expose Redis’s default port
EXPOSE 6379

# Use an absolute path so Docker can find it
ENTRYPOINT ["./entrypoint.sh"]

# Finally, default to running Redis
CMD ["redis-server", "--appendonly", "yes"]