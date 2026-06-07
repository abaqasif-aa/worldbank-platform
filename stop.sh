#!/bin/bash
echo "Stopping World Bank Platform..."
docker compose down
echo "Platform stopped. Data volumes preserved."
