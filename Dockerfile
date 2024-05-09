   # Use an official Python runtime as a parent image
   FROM python:3.8-slim-buster

   # Set the working directory in the container
   WORKDIR /app

   # Install any needed system packages
   RUN apt-get update && apt-get install -y libasound2 && rm -rf /var/lib/apt/lists/*

   # Copy the current directory contents into the container at /app
   COPY . /app

   # Install any needed packages specified in requirements.txt
   RUN pip install --no-cache-dir -r requirements.txt

   # Make port 8000 available to the world outside this container
   EXPOSE 8000

   # Define environment variable
   ENV Ai-Translation-Env

   # Run app.py when the container launches
   CMD ["gunicorn", "-w", "4", "-b", ":8000", "app:app"]