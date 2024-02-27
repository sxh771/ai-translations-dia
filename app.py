from flask import Flask, request, jsonify, render_template
from bs4 import BeautifulSoup
import requests
import os
import uuid
import fitz  # PyMuPDF

# checking environment variables
required_env_vars = ['AZURE_TRANSLATION_KEY', 'AZURE_TRANSLATION_ENDPOINT', 'AZURE_TRANSLATION_LOCATION']
for var in required_env_vars:
    if not os.environ.get(var):
        raise EnvironmentError(f"Missing required environment variable: {var}")
    
app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

def translate_text(text, key, endpoint, location):
    """Translate text using Azure Translation."""
    path = '/translate'
    constructed_url = endpoint + path

    params = {
        'api-version': '3.0',
        'from': 'fi',  # Finnish
        'to': ['en']  # English
    }

    headers = {
        'Ocp-Apim-Subscription-Key': key,
        'Ocp-Apim-Subscription-Region': location,
        'Content-type': 'application/json',
        'X-ClientTraceId': str(uuid.uuid4())
    }

    body = [{'text': text}]

    response = requests.post(constructed_url, params=params, headers=headers, json=body)
    if response.status_code == 200:
        return response.json()[0]['translations'][0]['text']
    else:
        # Handle errors or invalid responses
        return "Error: Unable to translate text"
        return response[0]['translations'][0]['text']

def is_translatable(element):
    """Check if the element should be translated."""
    blacklist = ['script', 'style', 'head', 'title', 'meta', '[document]']
    if element.name in blacklist or element.get('type') == 'text/javascript':
        return False
    return True

def translate_and_replace_large_segments(soup, key, endpoint, location):
    """Translate larger text segments within the HTML."""
    translatable_elements = soup.find_all(is_translatable)

    for element in translatable_elements:
        if element.text.strip():  # Check if the element contains non-whitespace text
            translated_text = translate_text(element.text, key, endpoint, location)
            element.string = translated_text



@app.route('/translate', methods=['POST'])
def translate():
    # Extract file from request
    input_file = request.files['file']
    
    # Check if the file is a PDF
    if input_file and input_file.filename.endswith('.pdf'):
        # Read the PDF
        doc = fitz.open(stream=input_file.read(), filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        
        # Translate the extracted text
        # Use environment variables for Azure credentials
        key = os.environ.get('AZURE_TRANSLATION_KEY')
        endpoint = os.environ.get('AZURE_TRANSLATION_ENDPOINT')
        location = os.environ.get('AZURE_TRANSLATION_LOCATION')
        
        translated_text = translate_text(text, key, endpoint, location)
        
        # For simplicity, returning the translated text directly
        return jsonify({"translated_text": translated_text}), 200
    else:
        return jsonify({"error": "Unsupported file type"}), 400

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    feedback = request.json['feedback']
    with open('feedback.txt', 'a') as file:
        file.write(f"{feedback}\n")
    
    return jsonify({"message": "Feedback submitted successfully!"}), 200


if __name__ == '__main__':
    app.run(debug=True)