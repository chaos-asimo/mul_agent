from fpdf import FPDF
import os

# 定义心经原文
jing_wen = """般若波罗蜜多心经

观自在菩萨，行深般若波罗蜜多时，照见五蕴皆空，度一切苦厄。

舍利子，色不异空，空不异色，色即是空，空即是色，受想行识，亦复如是。

舍利子，是诸法空相，不生不灭，不垢不净，不增不减。

是故空中无色，无受想行识，无眼耳鼻舌身意，无色声香味触法，无眼界，乃至无意识界。

无无明，亦无无明尽，乃至无老死，亦无老死尽。

无苦集灭道，无智亦无得。

以无所得故，菩提萨埵，依般若波罗蜜多故，心无挂碍，无挂碍故，无有恐怖，远离颠倒梦想，究竟涅槃。

三世诸佛，依般若波罗蜜多故，得阿耨多罗三藐三菩提。

故知般若波罗蜜多，是大神咒，是大明咒，是无上咒，是无等等咒，能除一切苦，真实不虚。

故说般若波罗蜜多咒，即说咒曰：

揭谛揭谛，波罗揭谛，波罗僧揭谛，菩提萨婆诃。"""

# 创建PDF对象
pdf = FPDF()
pdf.add_page()

# 注册中文字体
font_paths = [
    'C:/Windows/Fonts/msyh.ttc',      # 微软雅黑
    'C:/Windows/Fonts/simsun.ttc',    # 宋体
    'C:/Windows/Fonts/simhei.ttf',    # 黑体
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', # Linux 文泉驿
    '/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc',
]

font_path = None
for fp in font_paths:
    if os.path.exists(fp):
        font_path = fp
        break

if font_path:
    pdf.add_font('ChineseFont', '', font_path, uni=True)
    pdf.set_font('ChineseFont', '', 12)
else:
    pdf.set_font('Arial', '', 12)

# 设置标题
if font_path:
    pdf.set_font('ChineseFont', '', 16)
else:
    pdf.set_font('Arial', '', 16)

pdf.cell(0, 20, '般若波罗蜜多心经', ln=True, align='C')
pdf.ln(10)

# 设置正文内容
if font_path:
    pdf.set_font('ChineseFont', '', 14)
else:
    pdf.set_font('Arial', '', 14)

# 将文本按行分割，避免自动换行导致的对齐问题
lines = jing_wen.split('\n')
for line in lines:
    if line.strip(): # 跳过空行
        pdf.multi_cell(0, 10, line)
        pdf.ln(2) # 每段后增加一点间距

# 保存文件
pdf.output('xijing.pdf')
print("PDF已生成: xijing.pdf")