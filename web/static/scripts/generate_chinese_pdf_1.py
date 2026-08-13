from fpdf import FPDF

# 创建一个PDF对象
pdf = FPDF()

# 添加一页
pdf.add_page()

# 设置字体
pdf.set_font("Arial", size=12)

# 添加中文内容（需要确保系统中有支持中文的字体文件）
# 这里使用一个示例：添加一个简单的中文句子
pdf.cell(200, 10, txt="这是一个中文PDF文件示例。", ln=True, align='C')
pdf.cell(200, 10, txt="Hello, World! 这是第二行内容。", ln=True, align='C')

# 输出PDF文件
pdf.output("example.pdf")