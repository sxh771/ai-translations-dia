# HTML Translator Service

Welcome to the HTML Translator Service, a Flask-based application designed to streamline the process of translating HTML content from Finnish to English. Leveraging the power of Azure's Translation service, this tool is perfect for developers and content creators looking to efficiently localize web content for diverse audiences.

## Features

- **HTML Content Translation**: Seamlessly translates Finnish text within HTML files to English, ensuring your web content is accessible to a wider audience.
- **Azure Translation Integration**: Utilizes Azure's Translation service for high-quality, reliable translations.
- **Smart Content Filtering**: Excludes non-translatable elements (e.g., script, style, head, title, meta, and document tags) to focus on translating meaningful content.

## Getting Started

### Prerequisites

Ensure you have the following installed:

- Python 3.x
- Flask
- BeautifulSoup4
- Requests

Install all dependencies with:

```bash
pip install -r requirements.txt
```

### Configuration

Set up your Azure Translation service credentials by defining the following environment variables:

- `AZURE_TRANSLATION_KEY`: Your Azure Translation subscription key.
- `AZURE_TRANSLATION_ENDPOINT`: The endpoint URL of your Azure Translation service.
- `AZURE_TRANSLATION_LOCATION`: The location/region of your Azure Translation service.

### Running the Application

Launch the Flask application using:

```bash
python app.py
```

The service will be accessible at `http://localhost:5000`.

## Usage

To translate an HTML file, send a POST request to `http://localhost:5000/translate` with the HTML file as form-data. Use the key `file` for the file data.

Example using `curl`:

```bash
curl -X POST -F "file=@path/to/your/file.html" http://localhost:5000/translate
```

The response will be a JSON object containing the translated HTML content.

## Contributing

Contributions are welcome! Fork the repository, make your changes, and submit a pull request to help improve the application.

## Deployment

This application is deployable to Azure Web Apps, with a GitHub Actions workflow (`main_ai-translations.yml`) configured for CI/CD. This automates the build and deployment process, making it easy to get your translation service up and running in the cloud.

## Feedback and Ratings

The application supports submitting feedback and updating model ratings through the `/submit_feedback` and `/update_ratings` endpoints. This allows for user engagement and helps in refining the service based on user feedback.

For implementation details, refer to the `app.py` file.

Thank you for choosing the HTML Translator Service for your localization needs!