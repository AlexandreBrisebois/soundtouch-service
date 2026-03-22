FROM python:3.9-alpine

# Set the working directory
WORKDIR /workspace

# Install lightweight dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Provide a base config structure inside the container (can be mapped over)
COPY config.json ./

# Copy the structured application package
COPY app/ ./app/

# Forces python to immediately flush logs to stdout so they show in Docker logs
ENV PYTHONUNBUFFERED=1

# Expose the configurable Flask web server port
ENV PORT=5000
EXPOSE 5000

# Execute the main orchestrator module
ENTRYPOINT ["python", "-m", "app.main"]
