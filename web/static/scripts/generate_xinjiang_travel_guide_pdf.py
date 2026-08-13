import os
from fpdf import FPDF

# 安装依赖: pip install fpdf

class PDF(FPDF):
    def header(self):
        # 如果是第一页，不显示页眉
        if self.page_no() == 1:
            return
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, '新疆旅游攻略', 0, 0, 'L')
        self.cell(0, 10, f'第 {self.page_no()} 页', 0, 1, 'R')
        self.line(10, 20, 200, 20)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'生成日期: {__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 0, 'C')

def create_tourism_guide_pdf(filename="xinjiang_travel_guide.pdf"):
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # 添加中文字体支持 (FPDF默认不支持UTF-8中文，这里使用简易替代方案：英文描述或使用base64编码字体)
    # 注意：为了代码简洁且无需外部字体文件，本示例主要使用英文生成结构，
    # 实际生产环境中需要引入支持中文的库如 reportlab 或 fpdf2 并加载 .ttf 字体文件。
    # 此处为了演示逻辑，使用英文内容生成PDF。如果需要中文，请取消下方注释并配置字体。
    
    # --- 方案 B: 使用英文内容以确保无依赖直接运行 ---
    
    pdf.add_page()
    pdf.set_font('Arial', 'B', 24)
    pdf.cell(0, 20, 'Xinjiang Travel Guide', 0, 1, 'C')
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, 'A Comprehensive Guide to Exploring Xinjiang', 0, 1, 'C')
    pdf.ln(10)

    # Section 1: Introduction
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, '1. Introduction', 0, 1)
    pdf.set_font('Arial', '', 12)
    intro_text = (
        "Xinjiang Uygur Autonomous Region is located in the northwest of China. "
        "It is the largest provincial-level division in China, covering 1.66 million square kilometers. "
        "Known for its diverse landscapes, including mountains, deserts, grasslands, and lakes, "
        "Xinjiang offers a unique blend of natural beauty and rich cultural heritage."
    )
    pdf.multi_cell(0, 7, intro_text)
    pdf.ln(5)

    # Section 2: Best Time to Visit
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, '2. Best Time to Visit', 0, 1)
    pdf.set_font('Arial', '', 12)
    time_text = (
        "- Summer (June-August): Ideal for grasslands, lakes, and escaping the heat in the mountains.\n"
        "- Autumn (September-October): Best for photography, autumn foliage, and harvesting fruits.\n"
        "- Spring (April-May): Pleasant weather, blooming flowers, and fewer tourists.\n"
        "- Winter (November-March): Good for skiing and experiencing unique snowy landscapes."
    )
    pdf.multi_cell(0, 7, time_text)
    pdf.ln(5)

    # Section 3: Top Attractions
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, '3. Top Attractions', 0, 1)
    
    attractions = [
        ("Tianshan Tianchi (Heavenly Lake)", "A beautiful alpine lake surrounded by snow-capped mountains."),
        ("Kanas Lake", "Known for its mysterious legends and stunning turquoise waters."),
        ("Flaming Mountains", "Famous from the Journey to the West, known for its red sandstone cliffs."),
        ("Taklamakan Desert", "One of the largest sandy deserts in the world."),
        ("Kashgar Old City", "A vibrant hub of Uyghur culture, history, and cuisine.")
    ]
    
    for title, desc in attractions:
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 7, f"- {title}", 0, 1)
        pdf.set_font('Arial', '', 11)
        pdf.multi_cell(0, 6, f"  {desc}")
        pdf.ln(3)

    # Section 4: Local Cuisine
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, '4. Local Cuisine', 0, 1)
    pdf.set_font('Arial', '', 12)
    cuisine_text = (
        "Xinjiang is famous for its delicious food, influenced by Central Asian and Chinese cuisines.\n"
        "- Peking-style Roast Lamb (but actually Xinjiang style): Tender and flavorful.\n"
        "- Laghman: Hand-pulled noodles served with meat and vegetables.\n"
        "- Pilaf (Polo): Rice cooked with carrots, onions, and meat.\n"
        "- Naan: Traditional flatbread."
    )
    pdf.multi_cell(0, 7, cuisine_text)
    pdf.ln(5)

    # Section 5: Travel Tips
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, '5. Travel Tips', 0, 1)
    pdf.set_font('Arial', '', 12)
    tips_text = (
        "- Carry ID: ID cards are required for checkpoints and hotels.\n"
        "- Distance: Distances between cities can be very large; plan travel time accordingly.\n"
        "- Climate: The climate is dry and sunny; bring sunscreen and moisturizer.\n"
        "- Respect Local Customs: Xinjiang is home to many ethnic groups; respect their traditions."
    )
    pdf.multi_cell(0, 7, tips_text)

    # Save PDF
    pdf.output(filename)
    print(f"PDF guide generated successfully: {filename}")

if __name__ == "__main__":
    create_tourism_guide_pdf()