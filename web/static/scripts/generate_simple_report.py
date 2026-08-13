from fpdf import FPDF
import os

def generate_simple_report():
    # 创建PDF对象
    pdf = FPDF()
    pdf.add_page()

    # 注册中文字体（系统会自动查找微软雅黑、宋体等中文字体）
    font_paths = [
        'C:/Windows/Fonts/msyh.ttc',      # 微软雅黑
        'C:/Windows/Fonts/simsun.ttc',    # 宋体
        'C:/Windows/Fonts/simhei.ttf',    # 黑体
        '/System/Library/Fonts/PingFang.ttc', # macOS 苹方
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', # Linux 文泉驿
    ]
    font_path = None
    for fp in font_paths:
        if os.path.exists(fp):
            font_path = fp
            break

    if font_path:
        pdf.add_font('ChineseFont', '', font_path, uni=True)
        pdf.set_font('ChineseFont', '', 12)
        title_font = 'ChineseFont'
        body_font = 'ChineseFont'
    else:
        pdf.set_font('Arial', '', 12)
        title_font = 'Arial'
        body_font = 'Arial'

    # 设置标题
    pdf.set_font(title_font, '', 18)
    pdf.cell(0, 20, '示例报告文档', ln=True, align='C')
    pdf.ln(10)

    # 设置正文
    pdf.set_font(body_font, '', 12)
    
    content_lines = [
        "这是一个自动生成的示例PDF文档。",
        "",
        "主要内容包括：",
        "1. 文档标题",
        "2. 正文段落",
        "3. 项目列表",
        "",
        "您可以根据实际需求修改此脚本中的内容。",
        "如需添加更多页面，请调用 pdf.add_page()。",
        "",
        "感谢您的使用！"
    ]

    for line in content_lines:
        if line:
            pdf.multi_cell(0, 10, line)
        else:
            pdf.ln(5)

    # 保存文件
    output_filename = 'sample_report.pdf'
    pdf.output(output_filename)
    print(f"PDF已生成: {output_filename}")
    return output_filename

if __name__ == '__main__':
    generate_simple_report()