# -*- coding: utf-8 -*-
"""
中文PDF生成工具脚本
使用fpdf2库，支持中文显示
"""

import sys
import os
from fpdf import FPDF

def find_chinese_font():
    """查找系统中的中文字体"""
    font_paths = [
        # Windows 常见中文字体路径
        'C:/Windows/Fonts/msyh.ttc',      # 微软雅黑
        'C:/Windows/Fonts/msyhbd.ttc',    # 微软雅黑粗体
        'C:/Windows/Fonts/simsun.ttc',    # 宋体
        'C:/Windows/Fonts/simhei.ttf',    # 黑体
        'C:/Windows/Fonts/kaiu.ttf',      # 楷体
        'C:/Windows/Fonts/arialuni.ttf',  # Arial Unicode MS
        # macOS 字体路径
        '/Library/Fonts/Noto Sans CJK SC.ttc',
        '/Library/Fonts/Source Han Sans SC Regular.otf',
        # Linux 字体路径
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            return font_path
    return None

def generate_pdf(content: str, output_path: str, title: str = "文档"):
    """
    生成中文PDF文档
    
    Args:
        content: 文档内容（支持换行符分隔段落）
        output_path: 输出文件路径
        title: 文档标题
    """
    # 创建PDF对象
    pdf = FPDF()
    pdf.add_page()
    
    # 查找并注册中文字体
    font_path = find_chinese_font()
    
    if font_path:
        # 注册字体
        font_name = 'ChineseFont'
        pdf.add_font(font_name, '', font_path, uni=True)
        pdf.set_font(font_name, '', 12)
        pdf.set_font(font_name, '', 16)  # 标题字体大小
    else:
        # 如果没有找到中文字体，使用默认字体（可能无法显示中文）
        pdf.set_font('Arial', '', 12)
        pdf.set_font('Arial', '', 16)
        print("警告：未找到中文字体，中文可能无法正确显示")
    
    # 设置标题
    pdf.set_font(font_name if font_path else 'Arial', 'B', 18)
    pdf.cell(0, 20, title, ln=True, align='C')
    
    # 设置正文字体
    pdf.set_font(font_name if font_path else 'Arial', '', 12)
    pdf.ln(10)  # 换行
    
    # 处理内容，按段落分割
    paragraphs = content.split('\n')
    for para in paragraphs:
        # 去除首尾空白
        para = para.strip()
        if para:
            # 设置行高
            pdf.multi_cell(0, 12, para, align='L')
            pdf.ln(5)  # 段落间距
    
    # 保存PDF文件
    pdf.output(output_path)
    print(f"PDF文件已生成: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python generate_pdf.py <内容文件> <输出文件> [标题]")
        sys.exit(1)
    
    content_file = sys.argv[1]
    output_path = sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else "文档"
    
    with open(content_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    generate_pdf(content, output_path, title)