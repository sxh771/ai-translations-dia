import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, render_template, make_response, send_from_directory, abort, session
import os
import requests
import pyodbc
from datetime import datetime, timedelta
import uuid
import fitz  # PyMuPDF
import tempfile
import docx2txt
from azure.storage.blob import BlobServiceClient
import azure.cognitiveservices.speech as speechsdk

from urllib3 import disable_warnings, exceptions

# Disable SSL warnings
disable_warnings(exceptions.InsecureRequestWarning)

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

app.secret_key = 'your_secret_key_here'  # Set a secret key for session management

# environment = os.environ.get("ENVIRONMENT")

# Defining Azure AI Translation connections.
azure_translation_key = os.environ.get("AZURE_TRANSLATION_KEY")
azure_translation_endpoint = os.environ.get("AZURE_TRANSLATION_ENDPOINT")
azure_translation_location = os.environ.get(f"AZURE_TRANSLATION_LOCATION")

# # Configure Speech SDK 
speech_key = os.environ.get('AZURE_SPEECH_KEY')
speech_region = os.environ.get('AZURE_SPEECH_REGION')
speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
speech_config.speech_synthesis_voice_name = 'en-US-AvaNeural'
speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3)
speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

# Connection details from the Azure SQL Database
driver = 'ODBC Driver 18 for SQL Server'
server = os.environ.get("DB_SERVER")
database = os.environ.get("DB_NAME")
username = os.environ.get("DB_USERNAME")
password = os.environ.get("DB_PASSWORD")

connect_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
container_name = 'ai-translation'

# Check environment variables
required_env_vars = [
    "AZURE_TRANSLATION_KEY",
    "AZURE_TRANSLATION_ENDPOINT",
    "AZURE_TRANSLATION_LOCATION"
]
for var in required_env_vars:
    if not os.environ.get(var):
        logger.error(f"Missing required environment variable: {var}")
        raise EnvironmentError(f"Missing required environment variable: {var}")

def upload_file_to_blob(file_stream, file_name):
    connect_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    container_name = 'ai-translation'
    
    # Add datetime stamp to the file name
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    file_name_with_timestamp = f"{timestamp}_{file_name}"

    blob_service_client = BlobServiceClient.from_connection_string(connect_str)
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=file_name_with_timestamp)

    file_stream.seek(0)
    blob_client.upload_blob(file_stream, overwrite=True)

    blob_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{container_name}/{file_name_with_timestamp}"
    return blob_url

def extract_text_from_pdf(pdf_file):
    text = ""
    with fitz.open(stream=pdf_file.read(), filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()
    return text

def extract_text_from_docx(docx_file_stream):
    # Create a temporary file to save the uploaded .docx file
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        # Write the content of the uploaded file to the temporary file
        docx_file_stream.seek(0)  # Go to the beginning of the file stream
        tmp_file.write(docx_file_stream.read())
        # Use the path of the temporary file with docx2txt
        text = docx2txt.process(tmp_file.name)
    return text


# Default page.
@app.route('/')
def home():
    logger.info("Serving the home page.")
    return render_template('index.html')

def translate_text(text, azure_translation_key, azure_translation_endpoint, azure_translation_location, target_language):
    """Detect language and translate text using Azure Translation, handling large texts by splitting them into chunks."""
    logger.info("Starting language detection and text translation.")
    detect_language_path = '/detect'
    translate_path = '/translate'
    constructed_detect_url = azure_translation_endpoint + detect_language_path
    constructed_translate_url = azure_translation_endpoint + translate_path

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

    # Split text into chunks and translate
    chunk_size = 5000  # Adjust based on API limits
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    translated_chunks = []

    for chunk in chunks:
        params = {
            'api-version': '3.0',
            'from': detected_language,
            'to': [target_language]
        }
        translate_response = session.post(constructed_translate_url, params=params, headers=headers, json=[{'text': chunk}])
        if translate_response.status_code != 200:
            logger.error(f"Translation API error: {translate_response.text}")
            raise Exception("Error: Unable to translate text")
        translated_chunk = translate_response.json()[0]['translations'][0]['text']
        translated_chunks.append(translated_chunk)

    translated_text = ''.join(translated_chunks)
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
            created_at DATETIME2 DEFAULT GETDATE(),
            blob_url NVARCHAR(MAX),
            user_ip NVARCHAR(100)  -- Add this line
        )
    END
    ELSE
    BEGIN
        IF NOT EXISTS (SELECT * FROM sys.columns 
                       WHERE Name = N'created_at' AND Object_ID = Object_ID(N'TranslatedDocuments'))
        BEGIN
            ALTER TABLE TranslatedDocuments ADD created_at DATETIME2 DEFAULT GETDATE()
        END
        IF NOT EXISTS (SELECT * FROM sys.columns 
                       WHERE Name = N'blob_url' AND Object_ID = Object_ID(N'TranslatedDocuments'))
        BEGIN
            ALTER TABLE TranslatedDocuments ADD blob_url NVARCHAR(MAX)
        END
        IF NOT EXISTS (SELECT * FROM sys.columns 
                       WHERE Name = N'user_ip' AND Object_ID = Object_ID(N'TranslatedDocuments'))  -- Add this block
        BEGIN
            ALTER TABLE TranslatedDocuments ADD user_ip NVARCHAR(100)
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

# Directory where the synthesized audio files will be saved
audio_files_directory = os.path.join(app.root_path, 'audio_files')

# Create the directory if it does not exist
if not os.path.exists(audio_files_directory):
    os.makedirs(audio_files_directory)

# Global variable to track the last synthesis time
last_speech_synthesis_time = None
minimum_interval_seconds = 5  # Minimum allowed interval between syntheses

@app.route('/synthesize_speech', methods=['POST'])
def synthesize_speech():
    data = request.get_json()
    text = data['text']
    language = data['language']

    # Generate a unique filename for each synthesis request
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"output_{timestamp}.mp3"
    
    # Initialize the speech synthesizer with explicit voice and output format
    speech_key = os.environ.get('AZURE_SPEECH_KEY')
    speech_region = os.environ.get('AZURE_SPEECH_REGION')
    if not speech_key or not speech_region:
        raise ValueError("Azure speech service credentials are not set.")

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_synthesis_voice_name = 'en-US-JennyMultilingualNeural'
    speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3)
    
    audio_config = speechsdk.audio.AudioOutputConfig(filename=os.path.join(audio_files_directory, filename))
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
    
    # Perform the speech synthesis
    result = synthesizer.speak_text_async(text).get()
    
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        logger.info(f"Speech synthesized to '{filename}'")
        return jsonify({"message": "Speech synthesized successfully", "filename": filename}), 200
    else:
        logger.error("Speech synthesis failed.")
        return jsonify({"error": "Speech synthesis failed"}), 500

@app.route('/translate_and_insert', methods=['POST'])
def translate_and_insert():
    # Initialize blob_url to None
    blob_url = None
    
    extracted_text = ""
    # Check if text input is provided
    if 'text' in request.form and request.form['text'].strip():
        extracted_text = request.form['text'].strip()
        # Synthesize speech for the input text
        speech_synthesis_result = speech_synthesizer.speak_text_async(extracted_text).get()
        if speech_synthesis_result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            logger.error("Failed to synthesize speech for the input text.")
    # Check if a file is uploaded; this will override text input if both are provided
    if 'file' in request.files and request.files['file']:
        file = request.files['file']
        if file.filename.endswith('.pdf'):
            extracted_text = extract_text_from_pdf(file.stream)
        elif file.filename.endswith('.docx'):
            extracted_text = extract_text_from_docx(file.stream)
        elif file.filename.endswith('.txt'):
            extracted_text = file.stream.read().decode('utf-8')
        else:
            return jsonify({"error": "Unsupported file type"}), 400
        # Upload the file to Azure Blob Storage and get the blob URL
        blob_url = upload_file_to_blob(file.stream, file.filename)

    # Proceed with translation and database insertion as before
    # Ensure blob_url is handled correctly when it's None
    output_language = request.form['language']

    try:
        # Use 'extracted_text' instead of 'input_text'
        translated_text, detected_language = translate_text(extracted_text, azure_translation_key, azure_translation_endpoint, azure_translation_location, output_language)

        # Synthesize speech for the translated text
        speech_synthesis_result = speech_synthesizer.speak_text_async(translated_text).get()
        if speech_synthesis_result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            logger.error("Failed to synthesize speech for the translated text.")

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

        # Extract the user's IP address
        user_ip = request.remote_addr

        # Update your insert query to include the user_ip
        insert_query = """INSERT INTO TranslatedDocuments (input_text, detected_language, translated_text, output_language, blob_url, user_ip) VALUES (?, ?, ?, ?, ?, ?)"""

        # Include 'user_ip' in the cursor.execute call
        cursor.execute(insert_query, (extracted_text, detected_language, translated_text, output_language, blob_url if blob_url else "", user_ip))
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

@app.route('/update_ratings', methods=['POST'])
def update_ratings():
    data = request.get_json()
    action = data['action']
    
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
        "Connection Timeout=30;"
    )
    
    try:
        with pyodbc.connect(conn_str) as conn:
            with conn.cursor() as cursor:
                if action == "A is better":
                    cursor.execute("UPDATE ModelRatings SET ratingA = ratingA + 1 WHERE id = 1")
                elif action == "B is better":
                    cursor.execute("UPDATE ModelRatings SET ratingB = ratingB + 1 WHERE id = 1")
                elif action == "Tie":
                    cursor.execute("UPDATE ModelRatings SET ratingA = ratingA + 1, ratingB = ratingB + 1 WHERE id = 1")
                elif action == "Both are bad":
                    cursor.execute("UPDATE ModelRatings SET ratingA = ratingA - 1, ratingB = ratingB - 1 WHERE id = 1")
                conn.commit()
        return jsonify({"message": "Ratings updated successfully"}), 200
    except Exception as e:
        logger.error(f"Failed to update ratings: {e}")
        return jsonify({"error": "Failed to update ratings"}), 500

@app.route('/audio/<filename>')
def get_audio(filename):
    """Serve an audio file from the 'audio_files' directory."""
    if not os.path.exists(os.path.join(audio_files_directory, filename)):
        abort(404)  # Return a 404 if the file does not exist
    return send_from_directory(audio_files_directory, filename, mimetype='audio/mpeg')

if __name__ == '__main__':
    logger.info("Starting the Flask application...")
    app.run(debug=True)
