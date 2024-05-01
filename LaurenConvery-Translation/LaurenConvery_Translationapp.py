import pandas as pd
import os
import requests
import uuid

# Assuming the Azure Translator setup and credentials are already configured in your environment
def translate_text(text, target_language='zh-Hans'):
    """Translate text using Azure Translator."""
    azure_translation_key = os.environ.get("AZURE_TRANSLATION_KEY")
    azure_translation_endpoint = os.environ.get("AZURE_TRANSLATION_ENDPOINT")
    azure_translation_location = os.environ.get("AZURE_TRANSLATION_LOCATION")

    path = '/translate'
    constructed_url = azure_translation_endpoint + path

    headers = {
        'Ocp-Apim-Subscription-Key': azure_translation_key,
        'Ocp-Apim-Subscription-Region': azure_translation_location,
        'Content-type': 'application/json',
        'X-ClientTraceId': str(uuid.uuid4())
    }

    body = [{
        'text': text
    }]

    params = {
        'api-version': '3.0',
        'from': 'en',
        'to': [target_language]
    }

    response = requests.post(constructed_url, params=params, headers=headers, json=body)
    response.raise_for_status()
    return response.json()[0]['translations'][0]['text']

def translate_excel_columns(file_path, columns, target_language='zh-Hans', new_file_path=None):
    # Load the Excel file
    df = pd.read_excel(file_path, header=None)

        # Check if columns exist in the DataFrame
    missing_columns = [col for col in columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing columns in the Excel file: {missing_columns}")

    # Translate specified columns
    for column in columns:
        # Apply translation to each cell in the column if the cell is not NaN
        df[column] = df[column].apply(lambda x: translate_text(x, target_language) if pd.notna(x) else x)

    # Save the modified DataFrame to a new Excel file
    if new_file_path is None:
        new_file_path = file_path.replace('.xlsx', '_translated.xlsx')
    df.to_excel(new_file_path, index=False)

# Example usage
file_path = 'China.xlsx'
# columns_to_translate = ['N', 'O', 'P']  # Excel columns to translate
columns_to_translate = [13, 14, 15]  # Excel columns 'N', 'O', 'P' are 14th, 15th, and 16th columns (0-indexed)

new_file_path = 'China_translated.xlsx'  # Path for the new translated Excel file
translate_excel_columns(file_path, columns_to_translate, new_file_path=new_file_path)
