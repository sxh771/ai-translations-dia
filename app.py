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
from openai import AzureOpenAI

from flask import request, session, redirect
from msal import ConfidentialClientApplication


from urllib3 import disable_warnings, exceptions
# from system_prompt import system_prompt_instructions
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

from werkzeug.middleware.profiler import ProfilerMiddleware

app.config['PROFILE'] = True
app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[30])


import pandas as pd

# Load the Excel file to check its structure
file_path = 'Sherwin Acronyms-b8748681-2405-4e35-8e6a-c65a822a2feb.xlsx'
data = pd.read_excel(file_path)
terms_mapping = dict(zip(data['Column1'], data['Column2']))


# app.secret_key = 'your_secret_key_here'  # Set a secret key for session management

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

# Add a new AzureOpenAI client for model B
client_b = AzureOpenAI(
  api_key = os.getenv("AZURE_OPENAI_API_KEY"),  
  api_version = "2024-02-01",
  azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
)

# Connection details from the Azure SQL Database
driver = 'ODBC Driver 18 for SQL Server'
server = os.environ.get("DB_SERVER")
database = os.environ.get("DB_NAME")
username = os.environ.get("DB_USERNAME")
password = os.environ.get("DB_PASSWORD")

# Azure Blob Storage connection details
blob_connection_string = os.environ.get("BLOB_CONNECTION_STRING")
if not blob_connection_string:
    logger.error("BLOB_CONNECTION_STRING environment variable is not set.")
    raise ValueError("BLOB_CONNECTION_STRING environment variable is not set.")
blob_container_name = os.environ.get("BLOB_CONTAINER_NAME")
if not blob_container_name:
    logger.error("BLOB_CONTAINER_NAME environment variable is not set.")
    raise ValueError("BLOB_CONTAINER_NAME environment variable is not set.")

client_id = os.environ.get('AZURE_Translation_CLIENT_ID')
client_secret = os.environ.get('AZURE_Translation_CLIENT_SECRET')
tenant_id = os.environ.get('AZURE_TENANT_ID')

client_app = ConfidentialClientApplication(
    client_id=client_id,
    client_credential=client_secret,
    authority=f"https://login.microsoftonline.com/{tenant_id}"
)


microsoft_auth_url = client_app.get_authorization_request_url(scopes=["user.read"], redirect_uri="http://localhost:5000/auth/microsoft/callback")

# Default page.
@app.route('/')
def home():
    logger.info("Serving the home page.")
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Check if the user is authenticated with Microsoft SSO
        if 'microsoft_token' in session:
            # User is already authenticated, proceed with login logic
            pass  # Placeholder for the authentication logic
        else:
            # Redirect the user to the Microsoft login page
            return redirect(microsoft_auth_url)
    
    # Render the login page
    return render_template('login.html')


@app.route('/auth/microsoft/callback')
def microsoft_callback():
    # Handle the callback from Microsoft SSO
    auth_code = request.args.get('code')
    
    # Exchange the authorization code for an access token
    token_response = client_app.acquire_token_by_authorization_code(auth_code, scopes=["user.read"])
    
    # Store the access token in the session
    session['microsoft_token'] = token_response['access_token']
    
    # Redirect the user back to the login page
    return redirect('/login')



def translate_text(text, azure_translation_key, azure_translation_endpoint, azure_translation_location, target_language, terms_mapping=None):
    """Detect language and translate text using Azure Translation, handling large texts by splitting them into chunks."""
    logger.info("Starting language detection and text translation.")
    detect_language_path = '/detect'
    translate_path = '/translate'
    constructed_detect_url = azure_translation_endpoint + detect_language_path
    constructed_translate_url = azure_translation_endpoint + translate_path

    session = requests.Session()
    session.verify = False

    # if terms_mapping:
    #     # Convert all values in terms_mapping to strings
    #     terms_mapping = {term: str(placeholder) for term, placeholder in terms_mapping.items()}

    #     for term, placeholder in terms_mapping.items():
    #         text = text.replace(term, placeholder)
    
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

def extract_text_from_pdf(file_stream):
    """Extract text from a PDF file using PyMuPDF."""
    logger.info("Extracting text from PDF.")
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(file_stream.read())
        temp_file_path = temp_file.name

    with fitz.open(temp_file_path) as doc:
        text = ""
        for page in doc:
            text += page.get_text()

    os.remove(temp_file_path)
    return text

def extract_text_from_docx(file_stream):
    """Extract text from a DOCX file using docx2txt."""
    logger.info("Extracting text from DOCX.")
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(file_stream.read())
        temp_file_path = temp_file.name

    text = docx2txt.process(temp_file_path)

    os.remove(temp_file_path)
    return text

def upload_file_to_blob(file_stream, filename):
    """Upload a file to Azure Blob Storage and return the blob URL."""
    logger.info(f"Uploading file '{filename}' to Azure Blob Storage.")
    
    blob_service_client = BlobServiceClient.from_connection_string(blob_connection_string)
    # Ensure container name and blob name are not None
    if not blob_container_name or not filename:
        raise ValueError("Container name or blob name is missing.")
    blob_client = blob_service_client.get_blob_client(container=blob_container_name, blob=filename)

    file_stream.seek(0)
    blob_client.upload_blob(file_stream, overwrite=True)

    return blob_client.url

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
    filename = f"{timestamp}_{language}.mp3"

    global last_speech_synthesis_time
    current_time = datetime.now()

    if last_speech_synthesis_time is not None:
        elapsed_seconds = (current_time - last_speech_synthesis_time).total_seconds()
        if elapsed_seconds < minimum_interval_seconds:
            remaining_seconds = minimum_interval_seconds - elapsed_seconds
            return jsonify({"error": f"Please wait {remaining_seconds:.1f} seconds before making another request."}), 429

    last_speech_synthesis_time = current_time

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

@app.route('/update_ratings', methods=['POST'])
def update_ratings():
    data = request.get_json()
    action = data['action']
    
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

@app.route('/translate_and_insert', methods=['POST'])
def translate_and_insert():
    # Initialize blob_url to None
    blob_url = None
    
    # Load the Excel file to check its structure
    file_path = 'Sherwin Acronyms-b8748681-2405-4e35-8e6a-c65a822a2feb.xlsx'
    data = pd.read_excel(file_path)
    terms_mapping = dict(zip(data['Column1'], data['Column2']))

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
        # Preprocess the extracted text by replacing terms with placeholders
        preprocessed_text = extracted_text
        for term, placeholder in terms_mapping.items():
            preprocessed_text = preprocessed_text.replace(str(term), str(placeholder))        
        # Use 'extracted_text' instead of 'input_text'
        translated_text_a, detected_language = translate_text(
            text=preprocessed_text,
            azure_translation_key=azure_translation_key,
            azure_translation_endpoint=azure_translation_endpoint,
            azure_translation_location=azure_translation_location,
            target_language=output_language,
            terms_mapping=terms_mapping
        )        
        # Translation using model B
        try:
            chunks = [preprocessed_text[i:i+4096] for i in range(0, len(preprocessed_text), 4096)]
            translated_text_b = ""
            for chunk in chunks:
                response_b = client_b.chat.completions.create(
                    model="AI-Translation-Test",
                    messages=[
                        {"role": "system", "content": "You are a highly skilled multilingual translator with expertise in various technical domains. Your role is to accurately translate text between languages while preserving the meaning, context, and technical jargon specific to the given industry or field."},
                        {"role": "user", "content": f"Translate this to {output_language}: {chunk}"}
                    ]
                )
                translated_text_b += response_b.choices[0].message.content
        except Exception as e:
            logger.error(f"Failed to translate using model B: {e}")
            translated_text_b = "Translation failed"

                # Replace the placeholders back with the original terms in the translated texts from both models
        for term, placeholder in terms_mapping.items():
            translated_text_a = translated_text_a.replace(str(placeholder), str(term))
            translated_text_b = translated_text_b.replace(str(placeholder), str(term))

        # Synthesize speech for the translated text
        speech_synthesis_result = speech_synthesizer.speak_text_async(translated_text_a).get()
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
            "Connection Timeout=1500;"
        )

        # Ensure the table exists before inserting data
        ensure_table_exists(conn_str)

        # Connect to the database
        connection = pyodbc.connect(conn_str, pool_pre_ping=True, pool_size=10)
        cursor = connection.cursor()

        # Extract the user's IP address
        user_ip = request.remote_addr

        # Update your insert query to include the user_ip
        insert_query = """INSERT INTO TranslatedDocuments (input_text, detected_language, translated_text_a, translated_text_b, output_language, blob_url, user_ip) VALUES (?, ?, ?, ?, ?, ?, ?)"""

        # Include 'user_ip' in the cursor.execute call
        cursor.execute(insert_query, (extracted_text, detected_language, translated_text_a, translated_text_b, output_language, blob_url if blob_url else "", user_ip))
        connection.commit()

        return jsonify({
            "message": "Data inserted successfully",
            "translated_text_a": translated_text_a,
            "translated_text_b": translated_text_b,
            "detected_language": detected_language,
            "output_language": output_language
        }), 200

    except Exception as e:
        logger.error(f"Failed to translate and insert data: {e}")
        return jsonify({"error": "Failed to translate and insert data"}), 500

def ensure_table_exists(conn_str):
    create_table_query = """
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'TranslatedDocuments')
    CREATE TABLE TranslatedDocuments (
        input_text NVARCHAR(MAX),
        detected_language NVARCHAR(50),
        translated_text_a NVARCHAR(MAX),
        translated_text_b NVARCHAR(MAX),
        output_language NVARCHAR(50),
        blob_url NVARCHAR(MAX),
        user_ip NVARCHAR(50)
    );

    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_TranslatedDocuments_DetectedLanguage' AND object_id = OBJECT_ID('TranslatedDocuments'))
    CREATE NONCLUSTERED INDEX IX_TranslatedDocuments_DetectedLanguage ON TranslatedDocuments (detected_language);
    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_TranslatedDocuments_OutputLanguage' AND object_id = OBJECT_ID('TranslatedDocuments'))
    CREATE NONCLUSTERED INDEX IX_TranslatedDocuments_OutputLanguage ON TranslatedDocuments (output_language);
    """
    with pyodbc.connect(conn_str) as conn:
        with conn.cursor() as cursor:
            cursor.execute(create_table_query)
            conn.commit()

if __name__ == '__main__':
    logger.info("Starting the Flask application...")
    app.run(debug=True)
