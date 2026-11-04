#!/usr/bin/env bash
set -euo pipefail
mkdir -p data
curl -L -o data/metropt3.zip "https://archive.ics.uci.edu/static/public/791/metropt+3+dataset.zip"
unzip -o data/metropt3.zip -d data/
ls -lh data/