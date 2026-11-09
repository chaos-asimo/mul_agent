import os
import sys
import PyPDF2
import docx

def summarize_pdf(pdf_path):
    """Summarize a PDF file by extracting text."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"The file {pdf_path} does not exist.")
    
    text = ""
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
    
    # Simple summary: return the first 500 characters as a preview
    return text[:500] if text else "No text extracted."

def summarize_docx(docx_path):
    """Summarize a DOCX file by extracting text."""
    if not os.path.exists(docx_path):
        raise FileNotFoundError(f"The file {docx_path} does not exist.")
    
    document = docx.Document(docx_path)
    text = "\n".join([paragraph.text for paragraph in document.paragraphs])
    
    # Simple summary: return the first 500 characters as a preview
    return text[:500] if text else "No text extracted."

def summarize_file(file_path):
    """Summarize a file based on its extension."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file {file_path} does not exist.")
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.pdf':
        return summarize_pdf(file_path)
    elif ext == '.docx':
        return summarize_docx(file_path)
    elif ext == '.txt':
        with open(file_path, 'r', encoding='utf-8') as file:
            text = file.read()
        return text[:500] if text else "No text extracted."
    else:
        raise ValueError(f"Unsupported file type: {ext}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <file_path>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    try:
        summary = summarize_file(file_path)
        print(summary)
    except Exception as e:
        print(f"Error: {e}")