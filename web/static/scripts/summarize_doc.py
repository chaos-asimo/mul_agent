import os
import sys
import fitz  # PyMuPDF library for handling PDFs
import docx  # python-docx library for handling Word documents

def extract_text_from_pdf(file_path):
    """Extract text from a PDF file."""
    text = ""
    try:
        doc = fitz.open(file_path)
        for page in doc:
            text += page.get_text()
    except Exception as e:
        print(f"Error reading PDF: {e}")
    return text

def extract_text_from_docx(file_path):
    """Extract text from a DOCX file."""
    text = ""
    try:
        doc = docx.Document(file_path)
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
    except Exception as e:
        print(f"Error reading DOCX: {e}")
    return text

def summarize_text(text, max_length=500):
    """A simple summarization by taking the first few sentences/lines up to max_length."""
    if not text:
        return "No text found in the document."
    
    # Split into sentences or lines
    sentences = text.replace('\n', ' ').split('. ')
    
    summary = []
    current_length = 0
    
    for sentence in sentences:
        if current_length + len(sentence) <= max_length:
            summary.append(sentence)
            current_length += len(sentence)
        else:
            break
    
    return ". ".join(summary) + "."

def process_file(file_path):
    """Process the file based on its extension and return a summary."""
    if not os.path.exists(file_path):
        return "File not found."
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.pdf':
        text = extract_text_from_pdf(file_path)
    elif ext == '.docx':
        text = extract_text_from_docx(file_path)
    else:
        return "Unsupported file format. Only PDF and DOCX are supported."
    
    return summarize_text(text)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <file_path>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    summary = process_file(file_path)
    print(summary)