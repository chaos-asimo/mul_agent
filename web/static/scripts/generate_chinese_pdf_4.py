# 需要安装 fpdf2 库: pip install fpdf2
from fpdf import FPDF

class PDF(FPDF):
    def header(self):
        # 添加中文字体支持需要指定字体文件路径
        # 这里假设使用系统中常见的宋体或黑体，实际使用时请确保路径正确
        # Windows 示例: C:/Windows/Fonts/simsun.ttc
        # Mac 示例: /System/Library/Fonts/PingFang.ttc
        # Linux 示例: /usr/share/fonts/truetype/wqy/wqy-zenhei.ttc
        
        # 为了通用性，我们尝试加载一个常见的中文字体。
        # 注意：在真实环境中，你需要提供正确的字体文件路径(.ttf或.ttc)
        try:
            # 尝试加载 SimSun (宋体) - Windows 常见
            self.add_font('SimSun', '', 'C:/Windows/Fonts/simsun.ttc', uni=True)
        except:
            try:
                # 尝试加载 PingFang (苹方) - Mac 常见
                self.add_font('PingFang', '', '/System/Library/Fonts/PingFang.ttc', uni=True)
            except:
                # 如果找不到字体，抛出异常或提示用户
                raise Exception("无法找到中文字体文件。请根据操作系统修改字体路径。")
        
        self.set_font('SimSun', '', 12)
        self.cell(0, 10, '中文PDF示例', new_x="LMARGIN", new_y="NEXT", align='C')
        self.ln(5)

    def footer(self):
        # 设置页脚位置
        self.set_y(-15)
        self.set_font('SimSun', 'I', 8)
        self.cell(0, 10, f'页码 {self.page_no()}', align='C')

def generate_chinese_pdf(filename="chinese_output.pdf"):
    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # 设置中文字体
    pdf.set_font('SimSun', '', 14)
    
    # 添加标题
    pdf.cell(0, 10, '欢迎来到中文PDF文档', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(10)
    
    # 添加正文
    body_text = "这是一段中文文本。Python的FPDF库可以生成PDF文件。支持中文需要添加支持Unicode的中文字体。"
    pdf.set_font('SimSun', '', 12)
    # multi_cell 用于自动换行
    pdf.multi_cell(0, 10, body_text)
    pdf.ln(5)
    
    # 添加列表
    items = ["第一项", "第二项", "第三项"]
    pdf.set_font('SimSun', '', 12)
    for item in items:
        pdf.cell(10, 10, "-")
        pdf.cell(0, 10, item, new_x="LMARGIN", new_y="NEXT")
    
    # 保存PDF
    pdf.output(filename)
    print(f"PDF文件已生成: {filename}")

if __name__ == "__main__":
    generate_chinese_pdf()