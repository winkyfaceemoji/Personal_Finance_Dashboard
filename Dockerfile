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

# Expose the port.
EXPOSE 8050

# Command to run your app
CMD ["python", "app.py"]
