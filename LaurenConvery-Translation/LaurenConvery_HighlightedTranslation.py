import openpyxl
import os
import requests
import uuid

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

    body = [{'text': text}]

    params = {
        'api-version': '3.0',
        'from': 'en',
        'to': [target_language]
    }

    response = requests.post(constructed_url, params=params, headers=headers, json=body)
    response.raise_for_status()
    return response.json()[0]['translations'][0]['text']

def translate_highlighted_cells(file_path, target_language='zh-Hans', new_file_path=None):
    # Load the workbook and sheet
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active

    # Iterate through all cells in the worksheet
    for row in ws.iter_rows():
        for cell in row:
            # Check if the cell is highlighted
            if cell.fill.start_color.index != '00000000':  # '00000000' is the default color index for no fill
                if cell.value and isinstance(cell.value, str):
                    # Translate the text in the cell
                    translated_text = translate_text(cell.value, target_language)
                    cell.value = translated_text

    # Save the workbook to a new file
    if new_file_path is None:
        new_file_path = file_path.replace('.xlsx', '_translated.xlsx')
    wb.save(new_file_path)

# Example usage
file_path = 'China2.xlsx'
new_file_path = 'China2_Highlighted.xlsx'
translate_highlighted_cells(file_path, new_file_path=new_file_path)