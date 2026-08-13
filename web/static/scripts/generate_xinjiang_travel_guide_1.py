from fpdf import FPDF
import os

def generate_xinjiang_travel_guide():
    # 创建PDF对象
    pdf = FPDF()
    pdf.add_page()

    # 注册中文字体
    font_paths = [
        'C:/Windows/Fonts/msyh.ttc',      # 微软雅黑
        'C:/Windows/Fonts/simsun.ttc',    # 宋体
        'C:/Windows/Fonts/simhei.ttf',    # 黑体
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', # Linux 常见字体
        '/System/Library/Fonts/PingFang.ttc', # macOS 常见字体
    ]
    font_path = None
    for fp in font_paths:
        if os.path.exists(fp):
            font_path = fp
            break

    font_name = 'ChineseFont'
    if font_path:
        try:
            pdf.add_font(font_name, '', font_path, uni=True)
            pdf.set_font(font_name, '', 12)
        except:
            # 如果添加字体失败，回退到默认字体（可能无法显示中文）
            pdf.set_font('Arial', '', 12)
            font_name = 'Arial'
    else:
        pdf.set_font('Arial', '', 12)
        font_name = 'Arial'

    # --- 标题 ---
    pdf.set_font(font_name, '', 20)
    pdf.cell(0, 20, '新疆旅游攻略', ln=True, align='C')
    
    # --- 副标题/简介 ---
    pdf.set_font(font_name, 'B', 14)
    pdf.cell(0, 10, '探索大美新疆', ln=True)
    
    pdf.set_font(font_name, '', 12)
    pdf.multi_cell(0, 8, '新疆维吾尔自治区位于中国西北边陲，面积166万平方公里，占中国陆地总面积的六分之一。这里地域辽阔，景色壮丽，拥有雪山、草原、沙漠、湖泊等多样地貌，是摄影和自驾爱好者的天堂。')
    pdf.ln(5)

    # --- 最佳旅行时间 ---
    pdf.set_font(font_name, 'B', 14)
    pdf.cell(0, 10, '1. 最佳旅行时间', ln=True)
    pdf.set_font(font_name, '', 12)
    
    time_content = [
        "5月-6月：伊犁草原花开，气候宜人，适合赏花和徒步。",
        "7月-8月：瓜果飘香，夏季避暑胜地，南疆色彩斑斓。",
        "9月-10月：秋季最美，胡杨林金黄，喀纳斯色彩丰富。",
        "11月-次年3月：冬季冰雪游，适合滑雪和观赏雪景。"
    ]
    for item in time_content:
        pdf.cell(5) # 缩进
        pdf.multi_cell(0, 8, item)
    pdf.ln(5)

    # --- 经典路线推荐 ---
    pdf.set_font(font_name, 'B', 14)
    pdf.cell(0, 10, '2. 经典路线推荐', ln=True)
    pdf.set_font(font_name, '', 12)
    
    routes = [
        "【北疆环线】乌鲁木齐 - 天山天池 - 布尔津 - 喀纳斯 - 禾木 - 赛里木湖 - 乌鲁木齐",
        "   特点：自然风光绝美，湖泊、森林、雪山交织。",
        "",
        "【南疆风情】乌鲁木齐 - 库尔勒 - 库车大峡谷 - 塔克拉玛干沙漠公路 - 喀什古城 - 帕米尔高原",
        "   特点：人文风情浓郁，历史遗迹丰富，异域风情独特。",
        "",
        "【东疆美食】吐鲁番 - 鄯善 - 哈密",
        "   特点：品尝葡萄、哈密瓜，了解丝绸之路文化。"
    ]
    for item in routes:
        pdf.cell(5)
        pdf.multi_cell(0, 8, item)
    pdf.ln(5)

    # --- 必去景点 ---
    pdf.set_font(font_name, 'B', 14)
    pdf.cell(0, 10, '3. 必去景点', ln=True)
    pdf.set_font(font_name, '', 12)
    
    spots = [
        "1. 喀纳斯湖：被誉为‘人间仙境’，秋景尤为壮观。",
        "2. 赛里木湖：大西洋最后一滴眼泪，湖水湛蓝清澈。",
        "3. 天山天池：高山湖泊，传说中西王母沐浴之地。",
        "4. 喀什古城：维吾尔族风情浓郁，适合漫步拍照。",
        "5. 独库公路：连接南北疆的网红公路，四季风景各异。",
        "6. 火焰山：《西游记》中的经典场景，炎热干燥。"
    ]
    for item in spots:
        pdf.cell(5)
        pdf.multi_cell(0, 8, item)
    pdf.ln(5)

    # --- 美食推荐 ---
    pdf.set_font(font_name, 'B', 14)
    pdf.cell(0, 10, '4. 美食推荐', ln=True)
    pdf.set_font(font_name, '', 12)
    
    foods = [
        "烤羊肉串：外焦里嫩，香气扑鼻。",
        "大盘鸡：鸡肉与土豆的完美搭配，汤汁浓郁。",
        "手抓饭：米饭油亮，配有胡萝卜、洋葱和羊肉。",
        "拉条子：新疆特有的面食，口感筋道。",
        "哈密瓜/葡萄：甜度极高，新鲜美味。"
    ]
    for item in foods:
        pdf.cell(5)
        pdf.multi_cell(0, 8, item)
    pdf.ln(5)

    # --- 旅行贴士 ---
    pdf.set_font(font_name, 'B', 14)
    pdf.cell(0, 10, '5. 旅行贴士', ln=True)
    pdf.set_font(font_name, '', 12)
    
    tips = [
        "1. 气候干燥：新疆昼夜温差大，请携带防晒霜、墨镜和保湿用品。",
        "2. 时差：新疆比内地晚约2小时日落，作息可适当调整。",
        "3. 交通：景点之间距离较远，建议自驾或包车。",
        "4. 尊重习俗：请尊重当地少数民族的风俗习惯和宗教信仰。",
        "5. 边防证：前往帕米尔高原等边境地区需办理边防证。"
    ]
    for item in tips:
        pdf.cell(5)
        pdf.multi_cell(0, 8, item)
    pdf.ln(5)

    # --- 页脚 ---
    pdf.ln(10)
    pdf.set_font(font_name, 'I', 10)
    pdf.cell(0, 10, '祝您在新疆旅途愉快！', ln=True, align='C')

    # 保存文件
    output_filename = 'xinjiang_travel_guide.pdf'
    pdf.output(output_filename)
    print(f"PDF已生成: {output_filename}")

if __name__ == '__main__':
    generate_xinjiang_travel_guide()