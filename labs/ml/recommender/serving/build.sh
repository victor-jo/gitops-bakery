#!/usr/bin/env bash
# Builds the recommender Bento and a host-arch Docker image; the model and catalog are read from MLflow and Garage at run time
set -euo pipefail
cd "$(dirname "$0")/.."
# Nothing is imported into the BentoML model store: the service loads the champion's arrays and the catalog when it starts
.venv-rec/bin/bentoml build -f serving/bentofile.yaml . --output tag | tail -1 > serving/.bento-tag
TAG=$(sed 's/^__tag__://' serving/.bento-tag)
.venv-rec/bin/bentoml containerize "$TAG" --platform "linux/$(uname -m | sed 's/x86_64/amd64/')" -t "movie-recommender:${TAG#*:}"
echo "image: movie-recommender:${TAG#*:}"
