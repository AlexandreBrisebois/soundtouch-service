FROM python:3.15.0-alpine3.24

# ICI packed-AAC HLS adapter (runtime opt-in, no FFmpeg network input).
RUN apk add --no-cache ffmpeg=8.1.2-r0

# Set the working directory
WORKDIR /workspace

# Install lightweight dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt



# Copy the structured application package
COPY app/ ./app/

# Forces python to immediately flush logs to stdout so they show in Docker logs
ENV PYTHONUNBUFFERED=1

# Expose the configurable Flask web server port
ENV PORT=9001
EXPOSE 9001

# Execute the main orchestrator module
ENTRYPOINT ["python", "-m", "app.main"]
