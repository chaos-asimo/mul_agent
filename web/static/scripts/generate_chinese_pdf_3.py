from fpdf import FPDF
import os
import platform

def get_system_fonts():
    """
    获取系统中的字体路径列表
    """
    fonts = []
    
    # Windows 系统字体路径
    if platform.system() == "Windows":
        font_dir = os.environ.get("WINDIR", "C:\\Windows") + "\\Fonts"
        if os.path.exists(font_dir):
            for file in os.listdir(font_dir):
                if file.lower().endswith((".ttf", ".otf", ".ttc", ".fon")):
                    fonts.append(os.path.join(font_dir, file))
    
    # macOS 系统字体路径
    elif platform.system() == "Darwin":
        font_paths = [
            "/System/Library/Fonts",
            "/Library/Fonts",
            os.path.expanduser("~/Library/Fonts")
        ]
        for path in font_paths:
            if os.path.exists(path):
                for file in os.listdir(path):
                    if file.lower().endswith((".ttf", ".otf")):
                        fonts.append(os.path.join(path, file))
    
    # Linux 系统字体路径
    elif platform.system() == "Linux":
        font_paths = [
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            os.path.expanduser("~/.local/share/fonts"),
            os.path.expanduser("~/.fonts")
        ]
        for path in font_paths:
            if os.path.exists(path):
                for root, dirs, files in os.walk(path):
                    for file in files:
                        if file.lower().endswith((".ttf", ".otf")):
                            fonts.append(os.path.join(root, file))
    
    return fonts

def find_chinese_font(fonts):
    """
    从字体列表中查找支持中文的字体
    """
    chinese_font_keywords = [
        "simhei", "sim sun", "simsun", "mingliu", "ms gothic",
        "microsoft yahei", "yahei", "fangsong", "kai", "sukai",
        "droid sans fallback", "noto sans cjk", "wqy", "wenquanyi",
        "source han sans", "source han serif", "hiragino", "heiti",
        "songti", "pingfang"
    ]
    
    chinese_fonts = []
    for font_path in fonts:
        font_name = font_path.lower()
        for keyword in chinese_font_keywords:
            if keyword in font_name:
                chinese_fonts.append(font_path)
                break
    
    return chinese_fonts

def generate_pdf_with_chinese_font(chinese_font_path, output_pdf, text_content):
    """
    使用指定中文字体生成PDF文件
    """
    pdf = FPDF()
    
    # 添加页面
    pdf.add_page()
    
    # 设置中文字体
    # 注意：fpdf2 需要正确设置字体才能显示中文
    pdf.add_font("ChineseFont", "", chinese_font_path, uni=True)
    pdf.set_font("ChineseFont", size=12)
    
    # 写入文字
    pdf.multi_cell(0, 10, text_content)
    
    # 保存PDF
    pdf.output(output_pdf)
    print(f"PDF文件已生成: {output_pdf}")

def main():
    print("正在扫描系统字体...")
    all_fonts = get_system_fonts()
    print(f"找到 {len(all_fonts)} 个字体文件")
    
    print("正在查找支持中文的字体...")
    chinese_fonts = find_chinese_font(all_fonts)
    
    if not chinese_fonts:
        print("未找到支持中文的字体，请安装中文字体（如宋体、黑体等）")
        return
    
    print(f"找到 {len(chinese_fonts)} 个支持中文的字体:")
    for i, font in enumerate(chinese_fonts[:10]):  # 只显示前10个
        print(f"  {i+1}. {font}")
    
    if len(chinese_fonts) > 10:
        print(f"  ... 以及其他 {len(chinese_fonts) - 10} 个字体")
    
    # 选择第一个可用的中文字体
    selected_font = chinese_fonts[0]
    print(f"\n使用字体: {selected_font}")
    
    # 测试文本
    test_text = "这是一个测试PDF文件，包含中文内容。\n\n中文支持良好。"
    
    output_pdf = "chinese_document.pdf"
    
    try:
        generate_pdf_with_chinese_font(selected_font, output_pdf, test_text)
    except Exception as e:
        print(f"生成PDF时出错: {e}")
        print("尝试使用备用方法...")
        
        # 备用方案：尝试使用fpdf2的内置CJK支持
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, "此方法可能无法正确显示中文")
            pdf.output("fallback_document.pdf")
            print("已生成备用PDF文件，但中文可能无法正确显示")
        except Exception as e2:
            print(f"备用方法也失败: {e2}")

if __name__ == "__main__":
    main()