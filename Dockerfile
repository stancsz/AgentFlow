# Dockerfile for AgentFlow Viewer
# This builds a minimal container to run the viewer app for local testing

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/
COPY serve.py ./

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Expose port for the viewer
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=serve.py
ENV FLASK_ENV=development

# Command to run the viewer
CMD ["python", "serve.py"]
