import datetime
from fpdf import FPDF

class TouristGuidePDF(FPDF):
    def header(self):
        # 添加字体以支持中文（如果系统中有中文字体）
        # 注意：在实际使用中，需要确保系统中有支持中文的字体文件，如 'simsun.ttc' 或 'msyh.ttc'
        try:
            self.add_font('SimHei', '', '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', uni=True)
            self.set_font('SimHei', '', 12)
        except Exception as e:
            # 如果找不到字体，尝试使用默认字体并警告
            print(f"Warning: Could not load Chinese font. PDF may not display Chinese correctly. Error: {e}")
            self.set_font('Arial', '', 12)
        
        self.cell(0, 10, '新疆暑期旅游攻略', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('SimHei', 'B', 14)
        self.set_text_color(0, 51, 102)  # 深蓝色
        self.cell(0, 10, title, 0, 1, 'L')
        self.ln(5)
        self.set_draw_color(0, 51, 102)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def chapter_body(self, body):
        self.set_font('SimHei', '', 11)
        self.set_text_color(50, 50, 50)  # 深灰色
        self.multi_cell(0, 7, body)
        self.ln()

    def add_bullet_point(self, text):
        self.set_font('SimHei', '', 11)
        self.set_text_color(50, 50, 50)
        # 添加项目符号
        self.cell(5)
        self.cell(5, 7, '•')
        self.multi_cell(0, 7, text)
        self.ln(2)

def generate_xinjiang_guide():
    pdf = TouristGuidePDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # 标题页内容
    pdf.set_font('SimHei', 'B', 24)
    pdf.set_text_color(0, 51, 102)
    pdf.ln(40)
    pdf.cell(0, 10, '新疆暑期旅游攻略', 0, 1, 'C')
    pdf.ln(10)
    pdf.set_font('SimHei', '', 14)
    pdf.cell(0, 10, f'生成日期: {datetime.datetime.now().strftime("%Y年%m月%d日")}', 0, 1, 'C')
    pdf.ln(20)
    pdf.set_font('SimHei', '', 12)
    pdf.cell(0, 10, '探索西域风情，感受壮丽山河', 0, 1, 'C')
    pdf.ln(20)
    pdf.set_font('SimHei', 'I', 10)
    pdf.cell(0, 10, '注意事项：本攻略仅供参考，请根据实际情况调整行程。', 0, 1, 'C')
    pdf.ln(40)
    
    # 目录
    pdf.add_page()
    pdf.chapter_title('目录')
    pdf.add_bullet_point('一、 最佳旅行时间与气候特点')
    pdf.add_bullet_point('二、 推荐景点')
    pdf.add_bullet_point('    1. 北疆风光')
    pdf.add_bullet_point('    2. 南疆风情')
    pdf.add_bullet_point('    3. 东疆特色')
    pdf.add_bullet_point('三、 交通指南')
    pdf.add_bullet_point('四、 美食推荐')
    pdf.add_bullet_point('五、 住宿建议')
    pdf.add_bullet_point('六、 行前准备与注意事项')
    pdf.ln(10)

    # 正文内容
    pdf.add_page()
    pdf.chapter_title('一、 最佳旅行时间与气候特点')
    pdf.chapter_body(
        '7-8月是新疆旅游的黄金季节。此时北疆草原绿意盎然，瓜果飘香；南疆气候相对干燥炎热，但景色独特。'
        '新疆地域辽阔，各地气候差异较大。北疆夏季平均气温在15-25摄氏度之间，凉爽宜人；南疆夏季气温较高，'
        '可达35摄氏度以上，需注意防晒和补水。昼夜温差大，早晚需备外套。'
    )

    pdf.chapter_title('二、 推荐景点')
    
    pdf.chapter_body('1. 北疆风光')
    pdf.add_bullet_point('喀纳斯湖：被誉为“人间仙境”，湖水颜色随季节和天气变化，景色绝美。')
    pdf.add_bullet_point('禾木村：中国最美六大古村落之一，清晨的晨雾和木屋构成一幅宁静的画卷。')
    pdf.add_bullet_point('赛里木湖：大西洋最后一滴眼泪，湖蓝清澈，周围草原花团锦簇。')
    pdf.add_bullet_point('那拉提草原：世界四大草原之一，空中草原景色壮丽，适合骑马和露营。')
    
    pdf.chapter_body('2. 南疆风情')
    pdf.add_bullet_point('喀什古城：充满异域风情的千年古城，感受维吾尔族文化。')
    pdf.add_bullet_point('帕米尔高原：高原湖泊、雪山冰川，慕士塔格峰雄伟壮观。')
    pdf.add_bullet_point('塔克拉玛干沙漠：世界第二大流动沙漠，体验沙漠越野和骆驼骑行。')
    
    pdf.chapter_body('3. 东疆特色')
    pdf.add_bullet_point('吐鲁番火焰山：西游记中提到的火焰山，地貌独特，气温极高。')
    pdf.add_bullet_point('葡萄沟：盛产葡萄，可品尝各种新鲜葡萄和葡萄干。')
    pdf.add_bullet_point('交河故城：保存完好的生土建筑城市遗址，历史价值极高。')

    pdf.chapter_title('三、 交通指南')
    pdf.chapter_body(
        '新疆地域广阔，景点之间距离较远。建议采用以下方式出行：\n'
        '1. 飞机：乌鲁木齐地窝堡国际机场是主要枢纽，可飞往各地州市。\n'
        '2. 火车：新疆铁路网发达，普速列车和动车组连接主要城市。\n'
        '3. 自驾：适合喜欢自由行的游客，但需注意路况和驾驶安全，部分偏远地区信号不佳。\n'
        '4. 包车/拼车：适合没有驾驶经验或不想自己开车的游客，可找当地旅行社或平台预订。\n'
        '建议提前规划路线，避免疲劳驾驶。'
    )

    pdf.chapter_title('四、 美食推荐')
    pdf.chapter_body('新疆美食丰富多样，不容错过：\n')
    pdf.add_bullet_point('烤羊肉串：外焦里嫩，香气四溢。')
    pdf.add_bullet_point('大盘鸡：鸡肉鲜嫩，土豆软糯，汤汁浓郁，配皮带面绝佳。')
    pdf.add_bullet_point('手抓饭：米饭油亮，羊肉酥烂，胡萝卜甘甜。')
    pdf.add_bullet_point('馕：新疆主食，种类多样，口感香脆或软糯。')
    pdf.add_bullet_point('拉条子（拌面）：手工制作的面条，劲道十足，搭配各种浇头。')
    pdf.add_bullet_point('瓜果：哈密瓜、葡萄、西瓜等，甜美多汁。')

    pdf.chapter_title('五、 住宿建议')
    pdf.chapter_body(
        '新疆住宿选择多样：\n'
        '1. 城市：乌鲁木齐、喀什等地有星级酒店和经济型酒店，设施完善。\n'
        '2. 景区附近：喀纳斯、赛里木湖等地有民宿、客栈，环境较好，但价格可能较高。\n'
        '3. 露营：草原和沙漠地区可体验露营，感受星空和自然。\n'
        '建议提前预订，尤其是暑期旺季。'
    )

    pdf.chapter_title('六、 行前准备与注意事项')
    pdf.chapter_body(
        '1. 证件：身份证、驾驶证（自驾）、边防证（前往边境地区如喀纳斯、帕米尔高原等可能需要的证件）。\n'
        '2. 衣物：夏季防晒衣、帽子、墨镜、防晒霜；早晚保暖外套；舒适的徒步鞋。\n'
        '3. 药品：晕车药、感冒药、肠胃药、创可贴、驱蚊水。\n'
        '4. 其他：充电宝、相机、常用洗漱用品。\n'
        '5. 尊重当地民族风俗和宗教信仰。\n'
        '6. 注意环境保护，不乱扔垃圾。\n'
        '7. 保持通讯畅通，告知家人行程。\n'
        '8. 购买旅游保险，保障自身安全。'
    )

    # 保存PDF
    filename = 'Xinjiang_Summer_Travel_Guide.pdf'
    pdf.output(filename)
    print(f"PDF generated successfully: {filename}")

if __name__ == '__main__':
    # 确保安装了 fpdf 库
    # 如果未安装，请运行: pip install fpdf
    try:
        generate_xinjiang_guide()
    except ImportError:
        print("Error: fpdf library is not installed. Please install it using 'pip install fpdf'.")
    except Exception as e:
        print(f"An error occurred: {e}")