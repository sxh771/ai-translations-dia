# Use an official Python runtime as a parent image
FROM python:3.8-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for audio handling by Azure Cognitive Services
RUN apt-get update && apt-get install -y libasound2

# Copy the requirements file
COPY requirements.txt ./

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Define environment variable
ENV NAME AITRANSLATION

# Run app.py when the container launches
CMD ["gunicorn", "-w", "4", "-b", ":8000", "app:app"]
