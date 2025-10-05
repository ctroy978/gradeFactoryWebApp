import os
import json
import fitz  # PyMuPDF
from dotenv import load_dotenv
from fpdf import FPDF

def load_api_keys():
    """
    Loads API keys from .env file and configures Google Cloud credentials.
    Returns the XAI API key for grading.
    """
    load_dotenv()
    
    # Groq (XAI) API Key
    xai_api_key = os.getenv("XAI_API_KEY")
    
    # Google Cloud Credentials for Vision API
    if not os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
        # Making a simplifying assumption that the credentials file is in the root
        # In a real app, this might need to be a configurable path
        if os.path.exists('gen-lang-client.json'):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'gen-lang-client.json'
        else:
            print("Warning: GOOGLE_APPLICATION_CREDENTIALS not set and gen-lang-client.json not found.")

    return xai_api_key

def extract_text_from_pdf(pdf_path):
    """
    Extracts text from a PDF file using PyMuPDF.
    """
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except FileNotFoundError:
        raise FileNotFoundError(f"Error: The file '{pdf_path}' was not found.")
    except Exception as e:
        raise IOError(f"Error reading PDF file '{pdf_path}': {e}")

def extract_data_from_json(json_path):
    """
    Extracts rubric data from a JSON file.
    Returns a dict with 'rubric', 'question', 'correct_answers'.
    """
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
            rubric = data.get('rubric', '')
            question = data.get('question', '')
            correct_answers = data.get('correct_answers', [])
            return {
                'rubric': rubric,
                'question': question,
                'correct_answers': correct_answers
            }
    except FileNotFoundError:
        raise FileNotFoundError(f"Error: The file '{json_path}' was not found.")
    except json.JSONDecodeError:
        raise ValueError(f"Error: The file '{json_path}' is not a valid JSON file.")
    except Exception as e:
        raise IOError(f"Error reading JSON file '{json_path}': {e}")

def get_rubric_data(rubric_path):
    """
    Extracts data from a rubric file (PDF or JSON).
    Returns a dict with 'rubric', 'question', 'correct_answers'.
    PDF rubrics only have rubric text, others empty.
    """
    if rubric_path.lower().endswith('.pdf'):
        rubric_text = extract_text_from_pdf(rubric_path)
        return {
            'rubric': rubric_text,
            'question': '',
            'correct_answers': []
        }
    elif rubric_path.lower().endswith('.json'):
        return extract_data_from_json(rubric_path)
    else:
        raise ValueError("Unsupported rubric file format. Please use a .pdf or .json file.")

def save_to_pdf(text, output_path):
    """
    Saves the given text to a PDF file.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    # Encode with latin-1 to handle potential unicode errors, replacing unknown chars
    pdf.multi_cell(0, 10, text.encode('latin-1', 'replace').decode('latin-1'))
    pdf.output(output_path)
