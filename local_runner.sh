#!/bin/bash

# Variables (Replace with your details)
GITHUB_PAT="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"
GITHUB_REPO="FonsecaGoncalo/ECS-Runner-Fleet"
IMAGE_NAME="ecs-github-runner"

# Build Docker Image
docker build -t ${IMAGE_NAME} .

# Generate Runner Token
RUNNER_TOKEN=$(curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: token ${GITHUB_PAT}" \
  https://api.github.com/repos/${GITHUB_REPO}/actions/runners/registration-token \
  | jq -r '.token')

# Run GitHub Runner Container
docker run \
  --name github-runner \
  -e RUNNER_NAME="my-runner" \
  -e RUNNER_REPOSITORY_URL="https://github.com/${GITHUB_REPO}" \
  -e RUNNER_TOKEN="${RUNNER_TOKEN}" \
  -e RUNNER_LABELS="default-runner" \
  ${IMAGE_NAME}:latest
