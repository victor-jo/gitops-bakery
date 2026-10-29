#!/usr/bin/env bash
# Fetches the upstream chapter-5 step code at a pinned commit and applies this lab's edits (Garage region, model alias)
set -euo pipefail
cd "$(dirname "$0")"
REPO=https://github.com/practical-mlops/chapter-5
COMMIT=332915b2f617e7fed8646b7c096653c87eed9d30
if [ ! -d chapter-5 ]; then
  git init -q chapter-5
  git -C chapter-5 fetch -q --depth 1 "$REPO" "$COMMIT"
  git -C chapter-5 checkout -q FETCH_HEAD
  git -C chapter-5 apply ../lab.patch
fi
echo "upstream code ready in $(pwd)/chapter-5"
