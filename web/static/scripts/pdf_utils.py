import PyPDF2

def merge_pdfs(input_pdfs, output_pdf):
    """
    合并多个PDF文件为一个
    :param input_pdfs: 包含输入PDF文件路径的列表
    :param output_pdf: 输出PDF文件的路径
    """
    pdf_writer = PyPDF2.PdfWriter()
    
    for pdf_file in input_pdfs:
        with open(pdf_file, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in range(len(pdf_reader.pages)):
                pdf_writer.add_page(pdf_reader.pages[page])
    
    with open(output_pdf, 'wb') as output_file:
        pdf_writer.write(output_file)

def split_pdf(input_pdf, output_prefix):
    """
    拆分PDF文件，每页保存为一个单独的PDF
    :param input_pdf: 输入PDF文件的路径
    :param output_prefix: 输出文件的前缀
    """
    pdf_reader = PyPDF2.PdfReader(input_pdf)
    
    for i, page in enumerate(pdf_reader.pages):
        pdf_writer = PyPDF2.PdfWriter()
        pdf_writer.add_page(page)
        output_filename = f"{output_prefix}_page_{i + 1}.pdf"
        with open(output_filename, 'wb') as output_file:
            pdf_writer.write(output_file)

def extract_text(input_pdf):
    """
    从PDF文件中提取文本内容
    :param input_pdf: 输入PDF文件的路径
    :return: 提取的文本内容
    """
    pdf_reader = PyPDF2.PdfReader(input_pdf)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text()
    return text

if __name__ == "__main__":
    # 示例用法：合并PDF
    # merge_pdfs(['file1.pdf', 'file2.pdf'], 'merged.pdf')

    # 示例用法：拆分PDF
    # split_pdf('input.pdf', 'output')

    # 示例用法：提取文本
    # text = extract_text('input.pdf')
    # print(text)
    pass