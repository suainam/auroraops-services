# Custom Ansible Test Image
# Extends default ansible-test image with project dependencies
FROM quay.io/ansible/ansible-test-base:latest

# Copy project requirements
COPY requirements.yml /tmp/requirements.yml

# Install Python dependencies
RUN pip install --no-cache-dir \
    pytest \
    pytest-xdist \
    pyyaml \
    cryptography \
    jmespath \
    passlib \
    redis \
    requests

# Install Ansible Collections from requirements.yml
RUN ansible-galaxy collection install -r /tmp/requirements.yml --force

# Set working directory
WORKDIR /root
