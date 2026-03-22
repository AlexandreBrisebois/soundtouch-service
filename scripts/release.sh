#!/bin/bash

# A helper script to easily tag and trigger the GitHub Action CI/CD pipeline

if [ -z "$1" ]; then
    echo "Usage: ./scripts/release.sh <version> \"[optional message]\""
    echo "Example: ./scripts/release.sh v1.0.1 \"Added new API feature\""
    exit 1
fi

VERSION=$1
MESSAGE=${2:-"Release version $VERSION"}

# Ensure the version starts with 'v' to match our GitHub Action trigger (v*.*.*)
if [[ $VERSION != v* ]]; then
  echo "Error: Version must start with 'v' (e.g., v1.0.1)"
  exit 1
fi

echo "=========================================="
echo " Preparing Release"
echo " Tag: $VERSION"
echo " Message: $MESSAGE"
echo "=========================================="

# Create the annotated tag
git tag -a "$VERSION" -m "$MESSAGE"

echo "Pushing $VERSION to GitHub to trigger the automated build..."
# Push the newly created tag to GitHub
git push origin "$VERSION"

echo "✅ Success! The GitHub Action should now be building your image on Docker Hub."
