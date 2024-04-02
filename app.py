import os
import uuid
import pyodbc
import logging
import fitz
import docx2txt
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from azure.storage.blob import BlobServiceClient
import requests
from requests import Session

import asyncio
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

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

connect_str = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
container_name = 'ai-translation'


# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Check environment variables
required_env_vars = ['AZURE_TRANSLATION_KEY', 'AZURE_TRANSLATION_ENDPOINT', 'AZURE_TRANSLATION_LOCATION']
for var in required_env_vars:
    if not os.environ.get(var):
        logger.error(f"Missing required environment variable: {var}")
        raise EnvironmentError(f"Missing required environment variable: {var}")


def upload_file_to_blob(file_stream, file_name):
    connect_str = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
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

# Using Meta Seamless model for Model B translation
from transformers import AutoProcessor, SeamlessM4Tv2ForTextToText

processor = AutoProcessor.from_pretrained("facebook/seamless-m4t-v2-large")
model = SeamlessM4Tv2ForTextToText.from_pretrained("facebook/seamless-m4t-v2-large")

async def translate_chunk_model_b(chunk, src_lang_code, target_lang_code):
    text_inputs = processor(text=chunk, src_lang=src_lang_code, return_tensors="pt")
    decoder_input_ids = model.generate(**text_inputs, tgt_lang=target_lang_code)[0].tolist()
    translated_chunk = processor.decode(decoder_input_ids, skip_special_tokens=True)
    return translated_chunk

async def translate_model_b_async(text, src_lang_code, target_lang_code):
    chunk_size = 1024
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    tasks = [translate_chunk_model_b(chunk, src_lang_code, target_lang_code) for chunk in chunks]
    translated_chunks = await asyncio.gather(*tasks)
    translated_text = " ".join(translated_chunks)
    return translated_text

async def upload_file_to_blob_async(file_stream, file_name):
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, upload_file_to_blob, file_stream, file_name)

async def extract_text_from_pdf_async(pdf_file):
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, extract_text_from_pdf, pdf_file)

async def extract_text_from_docx_async(docx_file_stream):
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, extract_text_from_docx, docx_file_stream)

async def translate_text_async(text, azure_translation_key, azure_translation_endpoint, azure_translation_location, target_language):
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, translate_text, text, azure_translation_key, azure_translation_endpoint, azure_translation_location, target_language)

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
            translated_text_a NVARCHAR(MAX),
            translated_text_b NVARCHAR(MAX),
            output_language NVARCHAR(100),
            created_at DATETIME2 DEFAULT GETDATE(),
            blob_url NVARCHAR(MAX),
            user_ip NVARCHAR(100)
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
                       WHERE Name = N'user_ip' AND Object_ID = Object_ID(N'TranslatedDocuments'))
        BEGIN
            ALTER TABLE TranslatedDocuments ADD user_ip NVARCHAR(100)
        END
        IF NOT EXISTS (SELECT * FROM sys.columns 
                       WHERE Name = N'translated_text_b' AND Object_ID = Object_ID(N'TranslatedDocuments'))
        BEGIN
            ALTER TABLE TranslatedDocuments ADD translated_text_b NVARCHAR(MAX)
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
async def translate_and_insert_async():

    # Initialize blob_url to None
    blob_url = None
    
    extracted_text = ""
    # Check if text input is provided
    if 'text' in request.form and request.form['text'].strip():
        extracted_text = request.form['text'].strip()
    # Check if a file is uploaded; this will override text input if both are provided
    if 'file' in request.files and request.files['file']:
        file = request.files['file']
        if file.filename.endswith('.pdf'):
            extracted_text = await extract_text_from_pdf_async(file.stream)
        elif file.filename.endswith('.docx'):
            extracted_text = await extract_text_from_docx_async(file.stream)
        elif file.filename.endswith('.txt'):
            extracted_text = file.stream.read().decode('utf-8')
        else:
            return jsonify({"error": "Unsupported file type"}), 400
        # Upload the file to Azure Blob Storage and get the blob URL
        blob_url = await upload_file_to_blob_async(file.stream, file.filename)

    output_language = request.form['language']

    # Mapping from Azure AI Translation codes to Model B 3-letter codes
    azure_to_model_b_map = {
        "en": "eng",  # English
        "es": "spa",  # Spanish
        "fr": "fra",  # French
        "fi": "fin",  # Finnish
        "ku": "ckb",  # Kurdish
        "pl": "pol",  # Polish
    }

    try:
        translated_text_a, detected_language = await translate_text_async(extracted_text, azure_translation_key, azure_translation_endpoint, azure_translation_location, output_language)
        
        # Assuming 'detected_language' is the code from Azure AI Translation
        detected_language_code = detected_language[:2]  # Extract the 2-letter code if necessary
        model_b_source_lang_code = azure_to_model_b_map.get(detected_language_code, "eng")  # Default to English if not found

        # Assuming 'output_language' is the target language selected by the user
        model_b_target_lang_code = azure_to_model_b_map.get(output_language, "eng")  # Default to English if not found

        # Now use model_b_source_lang_code and model_b_target_lang_code for Model B translation
        translated_text_b = await translate_model_b_async(extracted_text, model_b_source_lang_code, model_b_target_lang_code)

        # Define your connection string (adjusted for your application's needs)
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            "TrustServerCertificate=yes;"
            "Connection Timeout=120;"
        )

                # Ensure the table exists before inserting data
        ensure_table_exists(conn_str)

        # Connect to the database
        try:
            connection = pyodbc.connect(conn_str)
            cursor = connection.cursor()

            # Extract the user's IP address
            user_ip = request.remote_addr

            # Update your insert query to include the user_ip
            insert_query = """INSERT INTO TranslatedDocuments (input_text, detected_language, translated_text_a, translated_text_b, output_language, blob_url, user_ip) VALUES (?, ?, ?, ?, ?, ?, ?)"""

            # Include 'user_ip' in the cursor.execute call
            cursor.execute(insert_query, (extracted_text, detected_language, translated_text_a, translated_text_b, output_language, blob_url, user_ip))
            connection.commit()
            cursor.close()
            connection.close()

            logger.info("Translation and database insertion successful.")
            return jsonify({"translated_text_a": translated_text_a, "translated_text_b": translated_text_b}), 200
        except pyodbc.Error as e:
            logger.error(f"Database error: {e}")
            return jsonify({"error": "Database error"}), 500

    except Exception as e:
        logger.error(f"Translation or database insertion failed: {e}")
        return jsonify({"error": "Translation or database insertion failed"}), 500

@app.route('/submit_feedback', methods=['POST'])
async def submit_feedback_async():
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
