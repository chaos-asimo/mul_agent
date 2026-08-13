from fpdf import FPDF
import os

class PosterPDF(FPDF):
    def header(self):
        pass

    def footer(self):
        pass

def create_ai_writing_poster():
    # 创建A4尺寸竖版PDF (595.28 x 841.89 points)
    pdf = PosterPDF('P', 'mm', 'A4')
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    # 背景色 - 明亮的浅蓝色/白色渐变模拟
    # 背景填充为非常浅的蓝色，营造现代、清爽的学习氛围
    pdf.set_fill_color(240, 248, 255)  # AliceBlue
    pdf.rect(0, 0, pdf.w, pdf.h, 'F')

    # 装饰元素：顶部渐变条
    pdf.set_fill_color(65, 105, 225)  # RoyalBlue
    pdf.rect(0, 0, pdf.w, 60, 'F')
    
    # 装饰元素：底部强调条
    pdf.set_fill_color(220, 20, 60)  # Crimson Red for urgency
    pdf.rect(0, pdf.h - 80, pdf.w, 80, 'F')

    # 注册中文字体
    font_paths = [
        'C:/Windows/Fonts/msyh.ttc',      # 微软雅黑
        'C:/Windows/Fonts/simsun.ttc',    # 宋体
        'C:/Windows/Fonts/simhei.ttf',    # 黑体
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc', # Linux常见字体
    ]
    font_path = None
    for fp in font_paths:
        if os.path.exists(fp):
            font_path = fp
            break

    font_name = 'Arial'
    if font_path:
        pdf.add_font('ChineseFont', '', font_path, uni=True)
        font_name = 'ChineseFont'

    # --- 顶部标题区域 ---
    # 主标题: AI写作训练营
    pdf.set_font(font_name, 'B', 40)
    pdf.set_text_color(255, 255, 255) # White text on blue background
    pdf.set_xy(10, 25)
    pdf.cell(0, 40, 'AI写作训练营', ln=True, align='C')

    # 副标题装饰线
    pdf.set_draw_color(255, 255, 255)
    pdf.line(100, 75, pdf.w - 100, 75)

    # --- 中间核心内容区域 ---
    # 背景：模拟办公桌/电脑环境的抽象色块或留白
    # 这里使用白色圆角矩形框来突出文字，模拟卡片感
    y_start = 100
    border_color = (65, 105, 225)
    pdf.set_draw_color(*border_color)
    pdf.set_line_width(2)
    # 绘制一个大圆角矩形作为内容容器
    pdf.ellipse(30, y_start, pdf.w - 60, 450, 'D')
    
    # 内部背景色
    pdf.set_fill_color(255, 255, 255)
    pdf.ellipse(30, y_start, pdf.w - 60, 450, 'F')

    # 中间文字: 7天掌握高效内容创作
    pdf.set_font(font_name, 'B', 28)
    pdf.set_text_color(33, 33, 33) # Dark Gray
    pdf.set_xy(30, y_start + 100)
    
    # 分行显示，增加层次感
    pdf.cell(0, 30, '7天', ln=True, align='C')
    pdf.set_font(font_name, '', 24)
    pdf.cell(0, 30, '掌握高效', ln=True, align='C')
    pdf.set_font(font_name, 'B', 24)
    pdf.cell(0, 30, '内容创作', ln=True, align='C')

    # --- 底部行动呼吁区域 ---
    # 红色背景区域已在顶部绘制，现在添加文字
    y_bottom_start = pdf.h - 80
    pdf.set_font(font_name, 'B', 28)
    pdf.set_text_color(255, 255, 255) # White text on red background
    pdf.set_xy(30, y_bottom_start + 25)
    pdf.cell(0, 30, '限时免费报名', ln=True, align='C')

    # 添加小字说明增加真实感
    pdf.set_font(font_name, '', 12)
    pdf.set_text_color(230, 230, 230)
    pdf.set_xy(30, y_bottom_start + 60)
    pdf.cell(0, 10, '扫码加入，开启你的AI写作之旅', ln=True, align='C')

    # 保存文件
    filename = 'ai_writing_camp_poster.pdf'
    pdf.output(filename)
    print(f"海报已生成: {filename}")

if __name__ == '__main__':
    create_ai_writing_poster()