# 需要安装依赖库:
# pip install reportlab
# pip install matplotlib

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

def generate_chinese_pdf():
    """
    生成一个支持中文的PDF文件
    """
    # 创建一个PDF文件
    filename = "chinese_example.pdf"
    
    # 检查字体文件是否存在，如果不存在则尝试使用系统默认字体
    # 这里我们尝试使用常见的中文字体文件
    font_path = None
    font_names = [
        "SimHei",       # 黑体
        "SimSun",       # 宋体
        "Microsoft YaHei",  # 微软雅黑
        "Arial Unicode MS", # Arial Unicode MS
        "Noto Sans CJK SC", # Noto Sans CJK SC (如果有安装)
    ]
    
    # 尝试查找字体文件
    possible_paths = [
        "/System/Library/Fonts/PingFang.ttc",  # macOS
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",  # Linux
        "C:/Windows/Fonts/simhei.ttf",  # Windows
        "C:/Windows/Fonts/msyh.ttc",  # Windows 微软雅黑
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            font_path = path
            break
    
    if font_path is None:
        # 如果没有找到字体文件，尝试使用内置字体（不支持中文）
        print("警告: 未找到中文字体文件，生成的PDF可能无法正确显示中文。")
        print("请安装中文字体文件并更新font_path变量。")
        # 使用默认字体
        c = canvas.Canvas(filename)
        c.setFont("Helvetica", 12)
        c.drawString(100, 750, "Default font - Chinese may not display correctly")
        c.save()
        print(f"PDF文件已生成: {filename} (不含中文支持)")
        return

    # 注册中文字体
    # 根据字体文件扩展名选择正确的注册方式
    font_name = "ChineseFont"
    pdfmetrics.registerFont(TTFont(font_name, font_path))
    
    # 创建PDF文档
    c = canvas.Canvas(filename)
    
    # 设置字体
    c.setFont(font_name, 12)
    
    # 添加中文内容
    c.drawString(100, 750, "这是一个支持中文的PDF文件示例")
    c.drawString(100, 720, "中文内容：你好世界！")
    c.drawString(100, 690, "Python 是一种非常流行的编程语言")
    c.drawString(100, 660, "PDF 文档可以包含多种语言")
    
    # 添加一些英文内容作为对比
    c.setFont("Helvetica", 12)
    c.drawString(100, 600, "This is English text for comparison")
    c.drawString(100, 570, "English: Hello World!")
    
    # 保存PDF
    c.save()
    print(f"PDF文件已成功生成: {filename}")
    print(f"字体路径: {font_path}")

if __name__ == "__main__":
    generate_chinese_pdf()