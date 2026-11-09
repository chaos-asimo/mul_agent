import fpdf

# 使用 fpdf 库生成 PDF 文件
# 如果未安装，请运行: pip install fpdf

class PDF(fpdf.FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 12)
        self.cell(0, 10, '新疆旅游攻略', 0, 1, 'C')
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'第 {self.page_no()}/{{nb}} 页', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Helvetica', 'B', 14)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 10, title, 0, 1, 'L', 1)
        self.ln(4)

    def chapter_body(self, body):
        self.set_font('Helvetica', '', 11)
        self.multi_cell(0, 7, body)
        self.ln()

# 创建 PDF 对象
pdf = PDF()
pdf.alias_nb_pages()
pdf.add_page()

# 定义内容
title = "新疆旅游攻略"
introduction = (
    "新疆维吾尔自治区，简称新，位于中国西北地区，是中国面积最大的省级行政区。"
    "这里拥有壮丽的自然风光、丰富的历史文化以及多元的民族风情。"
    "本攻略将为您提供一份详细的新疆旅行指南。"
)

destinations = (
    "1. 乌鲁木齐：新疆首府，大巴扎是必去之地，可以体验浓郁的维吾尔族文化。\n"
    "2. 喀纳斯：位于阿勒泰地区，被誉为\"人间仙境\"，拥有神秘的湖怪传说和高山湖泊。\n"
    "3. 吐鲁番：火焰山、葡萄沟、交河故址，感受干燥气候下的独特魅力。\n"
    "4. 喀什古城：充满异域风情的老城，适合漫步和摄影。\n"
    "5. 伊犁河谷：赛里木湖、那拉提草原，风景如画，适合自驾。"
)

best_time = (
    "最佳旅行时间：5月至10月。\n"
    "- 5-6月：草原花开，气候宜人。\n"
    "- 7-8月：瓜果成熟，适合避暑。\n"
    "- 9-10月：秋叶金黄，摄影最佳季节。"
)

tips = (
    "旅行小贴士：\n"
    "- 新疆地域广阔，景点间距离较远，建议包车或自驾。\n"
    "- 昼夜温差大，请携带保暖衣物。\n"
    "- 尊重当地民族习俗和宗教信仰。\n"
    "- 提前了解边防证办理要求（如前往喀纳斯部分区域）。"
)

# 写入内容
pdf.chapter_title(title)
pdf.chapter_body(introduction)

pdf.chapter_title("主要景点推荐")
pdf.chapter_body(destinations)

pdf.chapter_title("最佳旅行时间")
pdf.chapter_body(best_time)

pdf.chapter_title("旅行小贴士")
pdf.chapter_body(tips)

# 生成 PDF 文件
pdf.output('Xinjiang_Travel_Guide.pdf')