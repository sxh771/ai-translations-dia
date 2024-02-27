from flask import Flask, request, jsonify, render_template
import requests
import os
import uuid
import fitz  # PyMuPDF
from datetime import datetime
import logging
from bs4 import BeautifulSoup

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

@app.route('/')
def home():
    logging.info("Serving the home page.")
    return render_template('index.html')

def translate_text(text, key, endpoint, location):
    """Translate text using Azure Translation."""
    logging.debug("Starting text translation.")
    path = '/translate'
    constructed_url = endpoint + path

    params = {
        'api-version': '3.0',
        'from': 'fi',
        'to': ['en']
    }

    headers = {
        'Ocp-Apim-Subscription-Key': key,
        'Ocp-Apim-Subscription-Region': location,
        'Content-type': 'application/json',
        'X-ClientTraceId': str(uuid.uuid4())
    }

    body = [{'text': text}]

    try:
        response = requests.post(constructed_url, params=params, headers=headers, json=body)
        if response.status_code == 200:
            logging.info("Text translation successful.")
            return response.json()[0]['translations'][0]['text']
        else:
            logging.error(f"Translation API error: {response.text}")
            return "Error: Unable to translate text"
    except Exception as e:
        logging.error(f"Exception during translation: {e}")
        return "Error: Unable to translate text"

@app.route('/translate', methods=['POST'])
def translate():
    logging.info("Received a request to translate a PDF document.")
    input_file = request.files['file']
    
    if input_file and input_file.filename.endswith('.pdf'):
        logging.debug("Starting to process the PDF file.")
        try:
            doc = fitz.open(stream=input_file.read(), filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            logging.debug("Finished processing the PDF file.")

            key = os.environ.get('AZURE_TRANSLATION_KEY')
            endpoint = os.environ.get('AZURE_TRANSLATION_ENDPOINT')
            location = os.environ.get('AZURE_TRANSLATION_LOCATION')
            
            translated_text = translate_text(text, key, endpoint, location)
            return jsonify({"translated_text": translated_text}), 200
        except Exception as e:
            logging.error(f"Error processing PDF: {e}")
            return jsonify({"error": "Failed to process PDF file"}), 500
    else:
        logging.warning("Unsupported file type submitted for translation.")
        return jsonify({"error": "Unsupported file type"}), 400

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