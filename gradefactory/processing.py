import os
import io
import re
import fitz  # PyMuPDF
import pypdfium2 as pdfium
from PIL import Image
from google.cloud import vision
import google.generativeai as genai
import requests

from .prompts import OCR_CORRECTION_PROMPT
from .utils import save_to_pdf

def get_text_from_image(client, image_content):
    """Detects text in an image using the Vision API."""
    image = vision.Image(content=image_content)
    response = client.document_text_detection(image=image)
    return response.full_text_annotation.text

def pdf_to_images(pdf_path):
    """Converts a PDF to a list of PIL images."""
    doc = pdfium.PdfDocument(pdf_path)
    for i in range(len(doc)):
        page = doc.get_page(i)
        bitmap = page.render(scale=2)  # Increase scale for better quality
        pil_image = bitmap.to_pil()
        
        img_byte_arr = io.BytesIO()
        pil_image.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        yield img_byte_arr

def fix_ocr_mistakes(text: str, xai_api_key: str) -> str:
    """
    Uses the Grok API to fix OCR mistakes in the given text.
    """
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {xai_api_key}"}
    full_prompt = f"{OCR_CORRECTION_PROMPT}\n\nInput text:\n{text}"
    data = {"messages": [{"role": "user", "content": full_prompt}], "model": "grok-4-fast-reasoning", "stream": False, "temperature": 0.7}
    response = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=data)
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']

def run_processing(input_folder: str, output_folder: str, name_flag: bool = True, xai_api_key=None):
    """
    Processes all PDFs in the input folder, performs OCR, corrects the text,
    and saves them to the output folder.
    """
    print("--- Starting OCR and Text Correction Process ---")

    # Set up the Vision API client
    try:
        client = vision.ImageAnnotatorClient()
    except Exception as e:
        raise RuntimeError(f"Failed to create Google Cloud Vision client. Check credentials. Error: {e}")

    if not os.path.isdir(output_folder):
        os.makedirs(output_folder)

    pdf_files = [f for f in os.listdir(input_folder) if f.lower().endswith(".pdf")]

    for filename in pdf_files:
        input_path = os.path.join(input_folder, filename)
        print(f"\nProcessing: {input_path}")

        try:
            # 1. Convert each page of the PDF to an image and get OCR text
            for i, image_bytes in enumerate(pdf_to_images(input_path)):
                print(f"  - Processing page {i+1}...")
                raw_text = get_text_from_image(client, image_bytes)

                if not raw_text.strip():
                    print(f"  - Warning: No text found on page {i+1} of {filename}. Skipping.")
                    continue

                # 2. Correct the OCR text
                print("  - Correcting OCR mistakes with AI...")
                corrected_text = fix_ocr_mistakes(raw_text, xai_api_key)

                # 3. Determine the output filename
                output_filename = f"{os.path.splitext(filename)[0]}_page_{i+1}.pdf"
                if name_flag:
                    match = re.search(r"^name:\s*(.*)", corrected_text, re.IGNORECASE | re.MULTILINE)
                    if match:
                        student_name = match.group(1).strip().lower().replace(' ', '_')
                        output_filename = f"{student_name}.pdf"
                
                output_path = os.path.join(output_folder, output_filename)

                # 4. Save the corrected text to a new PDF
                save_to_pdf(corrected_text, output_path)
                print(f"  - Successfully saved corrected essay to {output_path}")

        except Exception as e:
            print(f"An error occurred while processing {filename}: {e}")

    print("\n--- OCR and Text Correction Process Complete ---")
