#!/bin/bash

# Docker Swarm manages worker count
export WORKERS=1

cd /usr/src/predict-news-labels/

exec /usr/local/bin/gunicorn -b :80 -t 900 app:app
