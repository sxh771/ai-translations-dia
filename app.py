from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import requests
import os
import uuid

app = Flask(__name__)

@app.route('/')
def home():
    return "Welcome to the HTML Translator Service"

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

    response = requests.post(constructed_url, params=params, headers=headers, json=body).json()

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
    input_html_file = request.files['file']
    html_content = input_html_file.read().decode('utf-8')

    # Use environment variables for Azure credentials
    key = os.environ.get('AZURE_TRANSLATION_KEY')
    endpoint = os.environ.get('AZURE_TRANSLATION_ENDPOINT')
    location = os.environ.get('AZURE_TRANSLATION_LOCATION')

    soup = BeautifulSoup(html_content, 'html.parser')
    translate_and_replace_large_segments(soup, key, endpoint, location)

    # For simplicity, returning the translated HTML content directly
    return jsonify({"translated_html": str(soup)})

if __name__ == '__main__':
    app.run(debug=True)