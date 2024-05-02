import pandas as pd
import os
import requests
import uuid
import glob

# Assuming the Azure Translator setup and credentials are already configured in your environment
def translate_text(text, target_language='pt-BR'):
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

def translate_excel_columns(file_path, column_names, target_language='pt-BR', new_file_path=None):
    # Load the Excel file, ensuring the first row is used as the header
    df = pd.read_excel(file_path)

    # Debugging: Print the columns to check if they are read correctly
    print("Columns in DataFrame:", df.columns.tolist())

    # Check if the specified column names exist in the DataFrame
    missing_columns = [col for col in column_names if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing columns in the Excel file {file_path}: {missing_columns}")

    # Create a new DataFrame with only the specified columns
    df_selected = df[column_names].copy()

    # Translate the selected columns for all rows
    for column in column_names:
        df_selected[column] = df_selected[column].apply(lambda x: translate_text(x, target_language) if pd.notna(x) else x)

    # Update the original DataFrame with the translated values
    df.update(df_selected)

    # Save the modified DataFrame to a new Excel file
    if new_file_path is None:
        new_file_path = file_path.replace('.xlsx', '_translated.xlsx')
    df.to_excel(new_file_path, index=False)

def process_folder(folder_path):
    # Column names for 'N', 'O', 'P' in the Excel files
    column_names_to_translate = ['Test Script (Step-by-Step) - Step', 'Test Script (Step-by-Step) - Test Data', 'Test Script (Step-by-Step) - Expected Result']
    excel_files = glob.glob(os.path.join(folder_path, '*.xlsx'))

    for file_path in excel_files:
        new_file_path = file_path.replace('.xlsx', '_translated.xlsx')
        translate_excel_columns(file_path, column_names_to_translate, new_file_path=new_file_path)

# Example usage
folder_path = './Translation'
process_folder(folder_path)