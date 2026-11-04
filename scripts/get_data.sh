#!/usr/bin/env bash
# Download the MetroPT-3 dataset into data/ (it is never committed).
set -euo pipefail

mkdir -p data
curl --fail --location --output data/metropt3.zip \
  "https://archive.ics.uci.edu/static/public/791/metropt+3+dataset.zip"
unzip -o data/metropt3.zip -d data/
rm -f data/metropt3.zip
ls -lh data/
