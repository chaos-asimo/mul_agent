from fpdf import FPDF
import os

# 创建PDF对象
pdf = FPDF()
pdf.add_page()

# 注册中文字体（系统会自动查找微软雅黑、宋体等中文字体）
font_paths = [
    'C:/Windows/Fonts/msyh.ttc',      # 微软雅黑
    'C:/Windows/Fonts/simsun.ttc',    # 宋体
    'C:/Windows/Fonts/simhei.ttf',    # 黑体
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
pdf.set_font('ChineseFont' if font_path else 'Arial', '', 18)
pdf.cell(0, 20, '新疆旅游全攻略', ln=True, align='C')
pdf.ln(10)

# 设置正文
pdf.set_font('ChineseFont' if font_path else 'Arial', '', 12)

content = [
    "一、最佳旅游时间",
    "新疆地域辽阔，四季景色各异。",
    "- 春季 (4-5月)：伊犁杏花盛开，气候宜人。",
    "- 夏季 (6-8月)：草原最美，瓜果飘香，适合避暑。",
    "- 秋季 (9-10月)：胡杨林金黄，秋高气爽，摄影最佳季。",
    "- 冬季 (11-次年3月)：冰雪旅游，体验滑雪和温泉。",
    "",
    "二、经典路线推荐",
    "1. 北疆自然风光线：乌鲁木齐 - 可可托海 - 喀纳斯 - 禾木 - 白哈巴",
    "2. 南疆人文风情线：乌鲁木齐 - 库尔勒 - 喀什 - 奥依塔克 - 塔县",
    "3. 独库公路穿越线：独山子 - 乔尔玛 - 那拉提 - 巴音布鲁克 - 库车",
    "",
    "三、必去景点",
    "- 喀纳斯湖：神秘的“湖怪”传说，变色湖美景。",
    "- 赛里木湖：大西洋最后一滴眼泪，蓝色湖泊。",
    "- 吐鲁番火焰山：热尔达木盆地，葡萄沟清凉世界。",
    "- 喀什古城：千年古城，异域风情浓郁。",
    "- 伊犁草原：那拉提、喀拉峻，空中草原美景。",
    "",
    "四、美食推荐",
    "- 烤羊肉串：外焦里嫩，香气四溢。",
    "- 大盘鸡：鸡肉与土豆的完美融合。",
    "- 手抓饭：米饭油亮，羊肉软烂。",
    "- 烤包子：皮脆馅香，回味无穷。",
    "- 馕坑肉：特色烤制，肉质鲜美。",
    "",
    "五、旅行贴士",
    "1. 交通：新疆面积大，建议自驾或包车，注意路况。",
    "2. 气候：昼夜温差大，需准备厚外套，注意防晒。",
    "3. 证件：身份证必带，部分边境地区需办理边防证。",
    "4. 饮食：多食水果蔬菜，防止上火，注意饮食卫生。",
    "5. 尊重民族风俗：尊重当地维吾尔族等少数民族习俗。",
]

for line in content:
    if line == "":
        pdf.ln(5)
    elif line.startswith("一") or line.startswith("二") or line.startswith("三") or line.startswith("四") or line.startswith("五"):
        # 小标题加粗
        pdf.set_font('ChineseFont' if font_path else 'Arial', 'B', 14)
        pdf.cell(0, 10, line, ln=True)
        pdf.ln(3)
        pdf.set_font('ChineseFont' if font_path else 'Arial', '', 12)
    else:
        pdf.multi_cell(0, 10, line)
        pdf.ln(2)

# 保存文件
pdf.output('新疆旅游攻略.pdf')
print("PDF已生成: 新疆旅游攻略.pdf")