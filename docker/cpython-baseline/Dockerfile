# CinderX Performance Testing Environment
# Based on official Python 3.14 image

FROM python:3.14-slim

# Install minimal dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Create directories
RUN mkdir -p /root/benchmarks /results

# Set up working directory
WORKDIR /root

# Default command
CMD ["/bin/bash"]
