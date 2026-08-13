import PyPDF2

# 如果尚未安装PyPDF2，请先运行: pip install PyPDF2

def extract_text_from_pdf(pdf_path):
    """
    从PDF文件中提取文本内容
    
    Args:
        pdf_path (str): PDF文件路径
        
    Returns:
        str: 提取的文本内容
    """
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text
    except FileNotFoundError:
        return f"错误：找不到文件 {pdf_path}"
    except Exception as e:
        return f"错误：{str(e)}"

# 示例用法
if __name__ == "__main__":
    # 替换为实际的PDF文件路径
    pdf_file = "example.pdf"
    extracted_text = extract_text_from_pdf(pdf_file)
    print(extracted_text)