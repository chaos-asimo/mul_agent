from fpdf import FPDF
from fpdf.enums import XPos, YPos

pdf = FPDF()
# 加载中文字体 (需确保路径正确)
pdf.add_font('SimSun', '', 'C:/Windows/Fonts/simsun.ttf', uni=True)
pdf.set_font('SimSun', size=12)

pdf.add_page()
# 使用新 API 并指定中文字体
pdf.cell(0, 10, '新疆旅游攻略', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')