# HTML Translator Service

This repository contains a Flask application designed to translate HTML content from Finnish to English using Azure's Translation service. It's a simple yet powerful tool for translating large segments of text within HTML files, making it easier to localize web content for different audiences.

## Features

- **HTML Content Translation**: Translates all translatable text within an HTML file from Finnish to English.
- **Azure Translation Integration**: Utilizes Azure's Translation service for accurate and reliable translations.
- **Filtering Non-Translatable Elements**: Ignores script, style, head, title, meta, and document tags to ensure only relevant text is translated.

## Requirements

To run this application, you will need:

- Python 3.x
- Flask
- BeautifulSoup4
- Requests

You can install all the necessary dependencies by running:

bash
pip install -r requirements.txt


## Setup

Before running the application, you need to set up your Azure Translation service credentials. Set the following environment variables:

- `AZURE_TRANSLATION_KEY`: Your Azure Translation subscription key.
- `AZURE_TRANSLATION_ENDPOINT`: The endpoint URL of your Azure Translation service.
- `AZURE_TRANSLATION_LOCATION`: The location/region of your Azure Translation service.

## Running the Application

To start the Flask application, run:

bash
python app.py


The application will start on `http://localhost:5000`.

## Usage

To translate an HTML file, send a POST request to `http://localhost:5000/translate` with the HTML file as form-data. The file should be included with the key `file`.

Example using `curl`:

curl -X POST -F "file=@path/to/your/file.html" http://localhost:5000/translate


The response will be a JSON object containing the translated HTML content.

## Contributing

Contributions to improve the application are welcome. Please feel free to fork the repository, make changes, and submit a pull request.

