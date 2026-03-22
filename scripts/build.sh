#!/bin/bash
set -e

# Configuration 
# You can override these before running by doing: DOCKER_USERNAME="myname" ./scripts/build.sh
DOCKER_USERNAME=${DOCKER_USERNAME:-"your_dockerhub_username"}
IMAGE_NAME=${IMAGE_NAME:-"soundtouch-service"}
VERSION=${VERSION:-"latest"}

FULL_IMAGE_NAME="$DOCKER_USERNAME/$IMAGE_NAME:$VERSION"

echo "=========================================="
echo " Building Docker Image"
echo " Tag: $FULL_IMAGE_NAME"
echo "=========================================="

# Build the docker image locally using the Dockerfile in the root directory
docker build -t "$FULL_IMAGE_NAME" .

echo ""
echo "✅ Build successful!"
echo "To test this locally before deploying, you can run:"
echo "  docker run --rm -it --network=host $FULL_IMAGE_NAME"
