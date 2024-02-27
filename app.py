from flask import Flask, request, jsonify, render_template
import requests
import os
import uuid
import fitz  # PyMuPDF
from datetime import datetime
import logging
from bs4 import BeautifulSoup

from reportlab.lib.pagesizes import letter
from io import BytesIO

# Configure logging
logging.basicConfig(filename='app.log', level=logging.DEBUG, 
                    format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')

# Check environment variables
required_env_vars = ['AZURE_TRANSLATION_KEY', 'AZURE_TRANSLATION_ENDPOINT', 'AZURE_TRANSLATION_LOCATION']
for var in required_env_vars:
    if not os.environ.get(var):
        logging.error(f"Missing required environment variable: {var}")
        raise EnvironmentError(f"Missing required environment variable: {var}")


app = Flask(__name__)

def convert_txt_to_pdf(txt_content):
    """Convert text content to a PDF file object."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    text_obj = c.beginText(40, 750)
    for line in txt_content.split('\n'):
        text_obj.textLine(line)
    c.drawText(text_obj)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


@app.route('/')
def home():
    logging.info("Serving the home page.")
    return render_template('index.html')

def translate_text(text, key, endpoint, location):
    """Detect language and translate text using Azure Translation."""
    logging.debug("Starting language detection and text translation.")
    detect_language_path = '/detect'
    translate_path = '/translate'
    constructed_detect_url = endpoint + detect_language_path
    constructed_translate_url = endpoint + translate_path

    headers = {
        'Ocp-Apim-Subscription-Key': key,
        'Ocp-Apim-Subscription-Region': location,
        'Content-type': 'application/json',
        'X-ClientTraceId': str(uuid.uuid4())
    }

    # Detect language
    body = [{'text': text[:100]}]  # Use a sample of the text for language detection
    try:
        detect_response = requests.post(constructed_detect_url, headers=headers, json=body, params={'api-version': '3.0'})
        if detect_response.status_code == 200:
            detected_language = detect_response.json()[0]['language']
            logging.info(f"Detected language: {detected_language}")
        else:
            logging.error(f"Language detection API error: {detect_response.text}")
            return "Error: Unable to detect language"
    except Exception as e:
        logging.error(f"Exception during language detection: {e}")
        return "Error: Unable to detect language"

    # Translate text
    params = {
        'api-version': '3.0',
        'from': detected_language,
        'to': ['en']
    }

    # Split text into chunks
    max_chunk_size = 5000  # Adjust based on the API limit
    chunks = [text[i:i+max_chunk_size] for i in range(0, len(text), max_chunk_size)]
    translated_text = ""

    for chunk in chunks:
        body = [{'text': chunk}]
        try:
            translate_response = requests.post(constructed_translate_url, params=params, headers=headers, json=body)
            if translate_response.status_code == 200:
                translated_text += translate_response.json()[0]['translations'][0]['text']
            else:
                logging.error(f"Translation API error: {translate_response.text}")
                return "Error: Unable to translate text"
        except Exception as e:
            logging.error(f"Exception during translation: {e}")
            return "Error: Unable to translate text"
    
    logging.info("Text translation successful.")
    return translated_text

@app.route('/translate', methods=['POST'])
def translate():
    input_file = request.files['file']
    file_type = input_file.filename.split('.')[-1].lower()
    doc = None

    if file_type == 'txt':
        txt_content = input_file.read().decode('utf-8')
        pdf_buffer = convert_txt_to_pdf(txt_content)
        doc = fitz.open("pdf", pdf_buffer.read())
    elif file_type == 'pdf':
        doc = fitz.open(stream=input_file.read(), filetype="pdf")
    else:
        return jsonify({"error": "Unsupported file type"}), 400

    if doc is None:
        return jsonify({"error": "File processing failed"}), 500

    try:
        text = ""
        for page in doc:
            text += page.get_text()
        # Add your logic to translate text here
        translated_text = text  # Placeholder for the actual translation logic
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"translated_text": translated_text}), 200

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    feedback = request.json['feedback']
    logging.info("Received feedback submission.")
    try:
        time_submitted = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open('feedback.txt', 'a') as file:
            file.write(f"{time_submitted}: {feedback}\n")
        logging.info("Feedback successfully saved.")
        return jsonify({"message": "Feedback submitted successfully!"}), 200
    except Exception as e:
        logging.error(f"Failed to save feedback: {e}")
        return jsonify({"error": "Failed to submit feedback"}), 500

if __name__ == '__main__':
    app.run(debug=True)