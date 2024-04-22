
# Project Title: Proof of Concept for AI-Powered Translation

## Introduction

This repository hosts a Flask-based web application designed to demonstrate AI-powered translation capabilities, including language detection, text translation, and speech synthesis using Microsoft Azure Cognitive Services. This proof of concept illustrates the application of these technologies in real-world scenarios, making it a valuable tool for developers interested in multilingual applications.

## Features

- **Language Detection and Translation**: Uses Azure Translation to detect and translate text.
- **Speech Synthesis**: Implements Azure Speech SDK to generate audio from text.
- **Document Handling**: Supports uploading and processing of PDF and DOCX files for text extraction.
- **Azure Blob Storage**: Manages file storage securely and efficiently.
- **Logging**: Provides detailed logs for monitoring and debugging purposes.

## Getting Started

### Prerequisites

Ensure you have the following installed:
- Python 3.8 or newer
- Flask web framework
- All necessary libraries and packages listed in `requirements.txt`

### Installation

1. **Clone the Repository**:
   ```
   https://github.com/sohail-hosseini/ai-translations.git
   cd ai-translations.git
   ```

2. **Install Dependencies**:
   ```
   pip install -r requirements.txt
   ```

### Environment Variables

The application requires the configuration of several environment variables to function properly:

- **`AZURE_TRANSLATION_KEY`**: API key for accessing Microsoft Azure Translation Services.
- **`AZURE_SPEECH_KEY`**: API key for utilizing Microsoft Azure Speech Services.
- **`DB_SERVER`**: Hostname or IP address of the SQL database server.
- **`DB_USERNAME`**: Username for SQL database access.
- **`DB_PASSWORD`**: Password for SQL database access.
- **`BLOB_CONNECTION_STRING`**: Connection string for Azure Blob Storage, used for managing file uploads.

These variables should be set in your system's environment or stored in a `.env` file for local development. Ensure they are secured and not exposed in the code or public repositories.

### Database Setup

Execute the provided SQL script to configure the necessary tables and indexes in your SQL database. This setup is crucial for storing and retrieving data efficiently.

### Running the Application

To launch the application, run:
```
python app.py
```
This command starts the Flask server. Access the application by navigating to `http://localhost:5000/` in your web browser.

## Usage

### Endpoints

- **Homepage (`GET /`)**: Displays the application's homepage.
- **Synthesize Speech (`POST /synthesize_speech`)**: Takes JSON input with text and language, returns the path to the generated speech audio file.
- **Update Ratings (`POST /update_ratings`)**: Handles user feedback on translation models.
- **Fetch Audio File (`GET /audio/<filename>`)**: Retrieves a specific audio file.
- **Translate and Insert (`POST /translate_and_insert`)**: Translates provided text or document content and stores the results in the database.

### Example Request

Example of how to use the `/synthesize_speech` endpoint with `curl`:
```
curl -X POST -H "Content-Type: application/json" -d '{"text":"Hello, world!", "language":"en-US"}' http://localhost:5000/synthesize_speech
```

## Contributing

We welcome contributions from the community. Please open an issue to discuss significant changes before making a pull request. Make sure to update or add tests as necessary.

