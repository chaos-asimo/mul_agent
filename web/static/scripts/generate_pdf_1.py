from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def generate_pdf(filename="output.pdf"):
    """
    生成一个简单的PDF文件。
    需要安装 reportlab 库: pip install reportlab
    """
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    
    # 添加标题
    c.setFont("Helvetica-Bold", 24)
    c.drawString(100, height - 100, "Hello, World!")
    
    # 添加正文
    c.setFont("Helvetica", 12)
    c.drawString(100, height - 150, "这是一个由Python生成的简单PDF文件。")
    c.drawString(100, height - 170, "使用reportlab库创建。")
    
    # 保存文件
    c.save()
    print(f"PDF文件 '{filename}' 已成功生成。")

if __name__ == "__main__":
    generate_pdf()