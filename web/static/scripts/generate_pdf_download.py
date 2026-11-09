import os
import tempfile
from fpdf import FPDF

# 需要安装 fpdf 库: pip install fpdf

def generate_pdf_with_download_link(title: str, content: str, output_filename: str = "output.pdf"):
    """
    生成一个包含指定标题和内容的PDF文件，并返回其文件路径。
    注意：此函数仅在本地生成文件。要实现真正的“下载链接”，
    需要将此文件部署到Web服务器（如使用Flask/Django），
    并通过HTTP响应提供下载。
    这里我们模拟生成文件并返回路径，以便后续处理。
    """
    # 创建PDF对象
    pdf = FPDF()
    pdf.add_page()
    
    # 设置字体
    pdf.set_font("Arial", size=12)
    
    # 添加标题
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=title, ln=True, align='C')
    pdf.ln(10)  # 换行
    
    # 添加内容
    pdf.set_font("Arial", size=12)
    # 使用multi_cell来自动处理换行
    pdf.multi_cell(0, 10, txt=content)
    
    # 保存PDF文件
    pdf.output(output_filename)
    
    return os.path.abspath(output_filename)

if __name__ == "__main__":
    # 示例数据
    title = "示例文档标题"
    content = """这是一个示例PDF文档的内容。
它包含了多行文本，用于测试PDF生成功能。
您可以将任何文本内容放入这里。
    
第二段内容。
"""
    
    # 生成PDF文件
    file_path = generate_pdf_with_download_link(title, content, "example_document.pdf")
    
    print(f"PDF文件已生成: {file_path}")
    print("\n注意：要在Web环境中提供下载链接，您需要使用Web框架（如Flask）来发送此文件作为HTTP响应。")
    print("例如，在Flask中，您可以使用：")
    print('from flask import send_file')
    print('@app.route("/download")')
    print('def download_pdf():')
    print('    return send_file("example_document.pdf", as_attachment=True)')