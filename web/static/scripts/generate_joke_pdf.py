# 需要安装 reportlab 库: pip install reportlab
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO

def create_joke_pdf():
    # 创建一个内存中的字节流对象
    buffer = BytesIO()
    
    # 创建 PDF 对象
    c = canvas.Canvas(buffer, pagesize=letter)
    
    # 设置标题
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 750, "Here is a joke for you!")
    
    # 设置正文字体
    c.setFont("Helvetica", 12)
    
    # 笑话内容
    joke_lines = [
        "Why did the scarecrow win an award?",
        "",
        "Because he was outstanding in his field!",
        "",
        "Hope this made you smile! :)"
    ]
    
    # 写入笑话内容
    y_position = 700
    for line in joke_lines:
        c.drawString(72, y_position, line)
        y_position -= 20
    
    # 保存 PDF
    c.save()
    
    # 返回字节流，以便下载
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes

if __name__ == "__main__":
    # 生成 PDF 数据
    pdf_data = create_joke_pdf()
    
    # 在实际应用中，这里可以将 pdf_data 写入文件或通过 Web 框架发送给用户
    with open("joke.pdf", "wb") as f:
        f.write(pdf_data)
    
    print("笑话已保存为 joke.pdf")