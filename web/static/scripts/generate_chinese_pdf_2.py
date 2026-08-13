from fpdf import FPDF

def create_chinese_pdf(filename="chinese_document.pdf"):
    # 创建一个PDF对象
    pdf = FPDF()
    
    # 添加一页
    pdf.add_page()
    
    # 设置中文字体
    # 注意：fpdf2 默认不支持中文，需要手动添加支持中文的字体文件
    # 这里使用常见的中文字体：simhei.ttf (黑体)
    # 你需要确保当前目录下有 simhei.ttf 文件，或者提供正确的字体路径
    try:
        # 添加中文字体
        pdf.add_font("SimHei", "", "simhei.ttf", uni=True)
        pdf.set_font("SimHei", size=12)
        
        # 写入中文内容
        pdf.cell(0, 10, txt="你好，世界！", ln=True, align='C')
        pdf.cell(0, 10, txt="这是一个使用 fpdf2 生成的中文PDF文档。", ln=True, align='C')
        pdf.cell(0, 10, txt="Python 是一种非常流行的编程语言。", ln=True, align='C')
        pdf.cell(0, 10, txt="FPDF2 库可以用来生成PDF文件。", ln=True, align='C')
        
        # 保存PDF文件
        pdf.output(filename)
        print(f"PDF文件 '{filename}' 已成功生成。")
        
    except Exception as e:
        print(f"生成PDF时出错: {e}")
        print("请确保当前目录下存在 'simhei.ttf' 中文字体文件。")
        print("你可以从以下地址下载中文字体文件：")
        print("https://github.com/defunkt/ja-mac-fonts/blob/master/SimHei.ttf")

if __name__ == "__main__":
    create_chinese_pdf()