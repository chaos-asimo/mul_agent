import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

def create_xinjiang_travel_guide(filename="Xinjiang_Travel_Guide.pdf"):
    """
    生成新疆旅游攻略PDF文件
    注意：为了支持中文，需要系统中存在支持中文的字体文件。
    这里假设使用常见的 'simsun.ttc' (宋体) 或 'msyh.ttc' (微软雅黑)。
    如果运行环境没有这些字体，请修改 font_path 为您系统中存在的 .ttf 或 .ttc 字体路径。
    """
    
    # 1. 注册中文字体
    # 注意：不同操作系统字体路径不同
    # Windows: C:/Windows/Fonts/simsun.ttc 或 msyh.ttc
    # macOS: /System/Library/Fonts/PingFang.ttc 或 STSong.ttf
    # Linux: /usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf 或需要安装字体
    
    # 尝试设置字体路径，请根据实际环境修改
    font_path = "C:/Windows/Fonts/simsun.ttc" # Windows 示例
    font_name = "SimSun" # 字体在PDF中的名称
    
    # 如果字体文件不存在，尝试其他常见路径或报错
    if not os.path.exists(font_path):
        # 尝试 macOS 常见路径
        font_path = "/System/Library/Fonts/PingFang.ttc"
        font_name = "PingFang"
        
    if not os.path.exists(font_path):
        # 尝试 Linux 常见路径
        font_path = "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"
        font_name = "DroidSans"

    if not os.path.exists(font_path):
        raise FileNotFoundError("未找到支持中文的TTF/TTC字体文件。请检查 font_path 是否指向有效的字体文件。")

    pdfmetrics.registerFont(TTFont(font_name, font_path))

    # 2. 创建PDF画布
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    
    # 3. 定义内容样式
    title_font = font_name
    title_size = 24
    heading_font = font_name
    heading_size = 16
    body_font = font_name
    body_size = 12
    
    # 4. 写入内容
    y_position = height - 1 * inch
    
    # 标题
    c.setFont(title_font, title_size)
    c.drawString(1 * inch, y_position, "新疆旅游攻略")
    y_position -= 1.5 * inch
    
    # 简介
    c.setFont(body_font, body_size)
    intro_text = "新疆维吾尔自治区，位于中国西北边陲，面积166万平方公里，是中国面积最大的省级行政区。这里既有壮丽的自然风光，又有浓郁的多民族文化。本攻略为您精选新疆必去景点、最佳旅行时间及实用建议。"
    c.drawString(1 * inch, y_position, intro_text)
    y_position -= 2 * inch
    
    # 最佳旅行时间
    c.setFont(heading_font, heading_size)
    c.drawString(1 * inch, y_position, "1. 最佳旅行时间")
    y_position -= 1.2 * inch
    c.setFont(body_font, body_size)
    time_text = "• 春季 (4-5月)：伊犁杏花盛开，景色宜人。\n• 夏季 (6-8月)：避暑胜地，草原绿意盎然，瓜果飘香。\n• 秋季 (9-10月)：北疆金秋胡杨林，色彩斑斓，摄影天堂。\n• 冬季 (11-3月)：体验冰雪运动，欣赏雾凇美景。"
    c.drawString(1 * inch, y_position, time_text)
    y_position -= 3 * inch
    
    # 必去景点
    c.setFont(heading_font, heading_size)
    c.drawString(1 * inch, y_position, "2. 必去景点")
    y_position -= 1.2 * inch
    c.setFont(body_font, body_size)
    spots_text = "• 喀纳斯湖：被誉为“神的后花园”，拥有变幻莫测的湖怪传说和绝美秋色。\n• 吐鲁番火焰山：西游记中的著名场景，夏季气温极高，但葡萄沟清凉宜人。\n• 天山天池：高山湖泊，传说中西王母的沐浴池，景色秀丽。\n• 那拉提草原：世界四大草原之一，空中草原风光无限。\n• 喀什古城：充满异域风情的千年古城，感受维吾尔族文化魅力。"
    c.drawString(1 * inch, y_position, spots_text)
    y_position -= 3 * inch
    
    # 美食推荐
    c.setFont(heading_font, heading_size)
    c.drawString(1 * inch, y_position, "3. 美食推荐")
    y_position -= 1.2 * inch
    c.setFont(body_font, body_size)
    food_text = "• 烤羊肉串：外焦里嫩，香气扑鼻。\n• 手抓饭：米饭油亮，搭配胡萝卜、洋葱和羊肉，营养丰富。\n• 大盘鸡：鸡肉鲜嫩，土豆软糯，配上手擀面一绝。\n• 馕：新疆人的主食，种类繁多，口感酥脆。\n• 葡萄干：吐鲁番葡萄干闻名遐迩，香甜可口。"
    c.drawString(1 * inch, y_position, food_text)
    y_position -= 3 * inch
    
    # 实用建议
    c.setFont(heading_font, heading_size)
    c.drawString(1 * inch, y_position, "4. 实用建议")
    y_position -= 1.2 * inch
    c.setFont(body_font, body_size)
    tips_text = "• 交通：新疆地域辽阔，建议自驾或包车旅行，提前规划路线。\n• 气候：昼夜温差大，即使是夏季也需准备外套；气候干燥，注意补水防晒。\n• 证件：前往部分边境地区可能需要办理边防证，请提前咨询当地公安局。\n• 尊重文化：尊重当地少数民族的风俗习惯和宗教信仰。"
    c.drawString(1 * inch, y_position, tips_text)
    y_position -= 3 * inch
    
    # 页脚
    c.setFont(body_font, 10)
    c.drawString(1 * inch, 1 * inch, "祝您在新疆旅途愉快！")
    
    # 5. 保存PDF
    c.save()
    print(f"PDF文件 '{filename}' 已成功生成。")

if __name__ == "__main__":
    # 确保安装了 reportlab 库: pip install reportlab
    try:
        create_xinjiang_travel_guide()
    except Exception as e:
        print(f"生成PDF时发生错误: {e}")