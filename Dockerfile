# Use an official Python image as a starting point
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Copy only the requirements file first (better for caching)
COPY requirements.txt .

# Install dependencies directly (no need for .venv inside Docker)
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your code, including the Data folder
COPY . .

# Inside a container the server must listen on every interface or Docker
# can't forward the port. Keep it private on the host instead, by publishing
# to loopback only: docker run -p 127.0.0.1:8050:8050 ...
# Debug mode gives the hot reload the dev workflow (code mounted at /app)
# relies on.
ENV FINANCE_HOST=0.0.0.0 \
    FINANCE_DEBUG=1

# Expose the port.
EXPOSE 8050

# Command to run your app
CMD ["python", "main.py"]
