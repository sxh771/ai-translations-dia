  FROM python:3.8-slim-buster  

  # Set the working directory in the container
  WORKDIR /app

  # Copy the requirements file and install Python dependencies
  COPY requirements.txt ./
  RUN pip install --no-cache-dir -r requirements.txt

  # Copy the rest of your application code
  COPY . .

  # Expose the port the app runs on
  EXPOSE 8000

  # Command to run the application
  CMD ["gunicorn", "-w", "4", "-b", ":8000", "app:app"]