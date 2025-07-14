# Use the official AWS Lambda Python 3.13 runtime as base image
FROM public.ecr.aws/lambda/python:3.13

# Set labels for better container management
LABEL maintainer="University of Arizona CB2"
LABEL description="SensorFabric Lambda container for UltraHuman data processing"
LABEL version="3.2.2"

# Install system dependencies if needed
RUN dnf update -y && \
    dnf install -y gcc python3-devel && \
    dnf clean all && \
    rm -rf /var/cache/dnf

# Copy requirements file first for better Docker layer caching
COPY requirements.txt ${LAMBDA_TASK_ROOT}/

# Install Python dependencies with optimizations
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

# Copy the entire sensorfabric package
COPY sensorfabric/ ${LAMBDA_TASK_ROOT}/sensorfabric/

# Set up proper permissions
RUN chmod -R 755 ${LAMBDA_TASK_ROOT}/sensorfabric/

# Create directory for cache and temp files
RUN mkdir -p ${LAMBDA_TASK_ROOT}/.cache && \
    chmod 777 ${LAMBDA_TASK_ROOT}/.cache

# Set environment variables for Lambda optimization
ENV PYTHONPATH=${LAMBDA_TASK_ROOT}
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# The CMD will be overridden when building specific lambda functions
CMD ["sensorfabric.uh_upload.lambda_handler"]