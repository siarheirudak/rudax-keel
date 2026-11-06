#!/usr/bin/env bash
# Shard planner, artifact binding, and grading.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
python3 "$HERE/speed_cases.py" --suite shards
