import os
from fpdf import FPDF

# 如果没有安装 fpdf，请运行: pip install fpdf

class PDF(FPDF):
    def header(self):
        # 设置字体
        self.set_font('Arial', 'B', 12)
        # 标题
        self.cell(0, 10, 'Xinjiang Travel Report', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        # 页脚
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 14)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 10, title, 0, 1, 'L', 1)
        self.ln(4)

    def chapter_body(self, body):
        self.set_font('Arial', '', 11)
        self.multi_cell(0, 6, body)
        self.ln()

    def add_image(self, img_path, x, y, w, h):
        try:
            self.image(img_path, x, y, w, h)
        except Exception as e:
            # 如果图片不存在或无法加载，仅记录错误而不中断
            print(f"Warning: Could not load image {img_path}: {e}")

def generate_pdf(filename="xinjiang_travel_report.pdf"):
    # 创建 PDF 对象
    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # 添加内容
    pdf.chapter_title("Introduction")
    intro_text = (
        "Xinjiang, officially the Xinjiang Uygur Autonomous Region, is an autonomous region "
        "of the People's Republic of China (PRC). It is located in the northwest of the country, "
        "bordering Mongolia, Russia, Kazakhstan, Kyrgyzstan, Tajikistan, Afghanistan, Pakistan, "
        "and India. Xinjiang is the largest provincial-level division of China by area, "
        "covering 1.66 million square kilometers, approximately one-sixth of China's total territory. "
        "Its population is approximately 25.85 million as of 2020."
    )
    pdf.chapter_body(intro_text)

    pdf.chapter_title("Top Attractions")
    attractions_text = (
        "1. Tian Shan Tianchi (Heavenly Lake of the Tianshan Mountains): "
        "A high-altitude alpine lake located in the Tianshan Mountains, known for its beautiful scenery.\n"
        "2. Taklamakan Desert: One of the largest sandy deserts in the world, offering thrilling desert adventures.\n"
        "3. Kanas Lake: A freshwater lake in the Altay Prefecture, famous for its clear waters and surrounding forests.\n"
        "4. Turpan: Known for its hot climate, ancient cities, and grape valleys."
    )
    pdf.chapter_body(attractions_text)

    pdf.chapter_title("Cultural Highlights")
    culture_text = (
        "Xinjiang is home to diverse ethnic groups, including the Uyghurs, Kazakhs, and Mongols. "
        "The region has a rich cultural heritage, with traditional music, dance, and cuisine. "
        "The Silk Road passes through Xinjiang, adding historical significance to its cities and landmarks."
    )
    pdf.chapter_body(culture_text)

    pdf.chapter_title("Travel Tips")
    tips_text = (
        "- Best time to visit: Spring (April-May) and Autumn (September-October).\n"
        "- Local cuisine: Try lamb kebabs, pilaf, and naan bread.\n"
        "- Transportation: Domestic flights and high-speed trains connect major cities."
    )
    pdf.chapter_body(tips_text)

    pdf.chapter_title("Conclusion")
    conclusion_text = (
        "Xinjiang offers a unique blend of natural beauty, historical significance, and cultural diversity. "
        "Whether you're interested in adventure, history, or relaxation, Xinjiang has something to offer for every traveler."
    )
    pdf.chapter_body(conclusion_text)

    # 保存 PDF
    pdf.output(filename)
    return os.path.abspath(filename)

if __name__ == "__main__":
    try:
        file_path = generate_pdf()
        print(f"PDF generated successfully: {file_path}")
    except ImportError:
        print("Error: 'fpdf' library is not installed. Please install it using 'pip install fpdf'.")
    except Exception as e:
        print(f"An error occurred: {e}")