import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, render_template
import os
import requests
import pyodbc
from datetime import datetime
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create a file handler and set level to debug
log_file_path = os.path.join(os.getcwd(), 'app.log')
file_handler = RotatingFileHandler(log_file_path, maxBytes=1024 * 1024 * 100, backupCount=10)  # 100MB per file, max 10 files
file_handler.setLevel(logging.INFO)

# Create a logging format
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(file_handler)

app = Flask(__name__)
os.environ['CURL_CA_BUNDLE'] = ""

# Defining Azure AI Translation connections.
azure_translation_key = os.environ.get("AZURE_TRANSLATION_KEY")
azure_translation_endpoint = os.environ.get("AZURE_TRANSLATION_ENDPOINT")
azure_translation_location = os.environ.get("AZURE_TRANSLATION_LOCATION")

# Connection details from the Azure SQL Database
driver = 'ODBC Driver 18 for SQL Server'
server = os.environ.get("DB_SERVER")
database = os.environ.get("DB_NAME")
username = os.environ.get("DB_USERNAME")
password = os.environ.get("DB_PASSWORD")

# Check environment variables
required_env_vars = ['AZURE_TRANSLATION_KEY', 'AZURE_TRANSLATION_ENDPOINT', 'AZURE_TRANSLATION_LOCATION']
for var in required_env_vars:
    if not os.environ.get(var):
        logger.error(f"Missing required environment variable: {var}")
        raise EnvironmentError(f"Missing required environment variable: {var}")

# Default page.
@app.route('/')
def home():
    logger.info("Serving the home page.")
    return render_template('index.html')

def translate_text(text, azure_translation_key, azure_translation_endpoint, azure_translation_location, target_language):
    """Detect language and translate text using Azure Translation."""
    logger.info("Starting language detection and text translation.")
    detect_language_path = '/detect'
    translate_path = '/translate'
    constructed_detect_url = azure_translation_endpoint + detect_language_path
    constructed_translate_url = azure_translation_endpoint + translate_path

    # Create a session with SSL verification disabled
    session = requests.Session()
    session.verify = False

    headers = {
        'Ocp-Apim-Subscription-Key': azure_translation_key,
        'Ocp-Apim-Subscription-Region': azure_translation_location,
        'Content-type': 'application/json',
        'X-ClientTraceId': str(uuid.uuid4())
    }

    # Detect language
    body = [{'text': text[:100]}]  # Use a sample of the text for language detection
    detect_response = session.post(constructed_detect_url, headers=headers, json=body, params={'api-version': '3.0'})
    if detect_response.status_code != 200:
        logger.error(f"Language detection API error: {detect_response.text}")
        raise Exception("Error: Unable to detect language")
    detected_language = detect_response.json()[0]['language']
    logger.info(f"Detected language: {detected_language}")

    # Translate text
    params = {
        'api-version': '3.0',
        'from': detected_language,
        'to': [target_language]
    }
    translate_response = session.post(constructed_translate_url, params=params, headers=headers, json=[{'text': text}])
    if translate_response.status_code != 200:
        logger.error(f"Translation API error: {translate_response.text}")
        raise Exception("Error: Unable to translate text")
    translated_text = translate_response.json()[0]['translations'][0]['text']
    logger.info("Text translation successful.")

    return translated_text, detected_language

def ensure_table_exists(conn_str):
    create_table_query = """
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'TranslatedDocuments')
    BEGIN
        CREATE TABLE TranslatedDocuments (
            id INT PRIMARY KEY IDENTITY(1,1),
            input_text NVARCHAR(MAX),
            detected_language NVARCHAR(100),
            translated_text NVARCHAR(MAX),
            output_language NVARCHAR(100),
            created_at DATETIME2 DEFAULT GETDATE()
        )
    END
    ELSE
    BEGIN
        IF NOT EXISTS (SELECT * FROM sys.columns 
                       WHERE Name = N'created_at' AND Object_ID = Object_ID(N'TranslatedDocuments'))
        BEGIN
            ALTER TABLE TranslatedDocuments ADD created_at DATETIME2 DEFAULT GETDATE()
        END
    END
    """
    try:
        with pyodbc.connect(conn_str) as conn:
            with conn.cursor() as cursor:
                cursor.execute(create_table_query)
                conn.commit()
                logger.info("Checked/created/updated table 'TranslatedDocuments'.")
    except Exception as e:
        logger.error(f"Failed to check/create/update table: {e}")

def ensure_feedback_table_exists(conn_str):
    create_feedback_table_query = """
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Feedback')
    CREATE TABLE Feedback (
        id INT PRIMARY KEY IDENTITY(1,1),
        feedback_text NVARCHAR(MAX),
        created_at DATETIME2 DEFAULT GETDATE()
    )
    """
    try:
        with pyodbc.connect(conn_str) as conn:
            with conn.cursor() as cursor:
                cursor.execute(create_feedback_table_query)
                conn.commit()
                logger.info("Checked/created table 'Feedback'.")
    except Exception as e:
        logger.error(f"Failed to check/create 'Feedback' table: {e}")

@app.route('/translate_and_insert', methods=['POST'])
def translate_and_insert():
    logger.info("Starting translation and insertion process.")
    data = request.get_json()
    input_text = data['text']
    output_language = data['language']  # Since we're allowing users to select the language

    try:
        translated_text, detected_language = translate_text(input_text, azure_translation_key, azure_translation_endpoint, azure_translation_location, output_language)

        # Define your connection string (adjusted for your application's needs)
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            "TrustServerCertificate=yes;"
            "Connection Timeout=500;"
        )

        # Ensure the table exists before inserting data
        ensure_table_exists(conn_str)

        # Connect to the database
        connection = pyodbc.connect(conn_str)
        cursor = connection.cursor()

        # Insert data into the database
        insert_query = """INSERT INTO TranslatedDocuments (input_text, detected_language, translated_text, output_language) VALUES (?, ?, ?, ?)"""
        cursor.execute(insert_query, (input_text, detected_language, translated_text, output_language))
        connection.commit()

        return jsonify({"message": "Data inserted successfully", "translated_text": translated_text, "detected_language": detected_language, "output_language": output_language}), 200

    except Exception as e:
        logger.error(f"Failed to translate and insert data: {e}")
        return jsonify({"error": "Failed to translate and insert data"}), 500

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    data = request.get_json()
    feedback_text = data['feedback']

    try:
        # Define your connection string (adjusted for your application's needs)
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            "TrustServerCertificate=yes;"
            "Connection Timeout=30;"
        )

        # Ensure the Feedback table exists before inserting data
        ensure_feedback_table_exists(conn_str)

        # Connect to the database
        with pyodbc.connect(conn_str) as conn:
            with conn.cursor() as cursor:
                # Insert feedback into the database
                insert_query = """INSERT INTO Feedback (feedback_text) VALUES (?)"""
                cursor.execute(insert_query, (feedback_text,))
                conn.commit()

        logger.info("Feedback successfully saved.")
        return jsonify({"message": "Feedback submitted successfully"}), 200

    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}")
        return jsonify({"error": "Failed to submit feedback"}), 500

if __name__ == '__main__':
    logger.info("Starting the Flask application...")
    app.run(debug=True)
