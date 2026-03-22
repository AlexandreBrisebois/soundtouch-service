#!/bin/bash
set -e

# Configuration
# You can override these before running by doing: DOCKER_USERNAME="myname" ./scripts/deploy.sh
DOCKER_USERNAME=${DOCKER_USERNAME:-"your_dockerhub_username"}
IMAGE_NAME=${IMAGE_NAME:-"soundtouch-service"}
VERSION=${VERSION:-"latest"}

FULL_IMAGE_NAME="$DOCKER_USERNAME/$IMAGE_NAME:$VERSION"

echo "=========================================="
echo " Deploying (Pushing) to Docker Hub"
echo " Image: $FULL_IMAGE_NAME"
echo "=========================================="

# Authenticate if needed (Will prompt if not logged in)
# docker login

# Push the docker image to Docker Hub
docker push "$FULL_IMAGE_NAME"

echo ""
echo "✅ Deploy successful!"
echo "Your image is now live on Docker Hub at: hub.docker.com/r/$DOCKER_USERNAME/$IMAGE_NAME"
echo "You can now spin up this container on your Synology NAS using the deployment/docker-compose.yml file!"
