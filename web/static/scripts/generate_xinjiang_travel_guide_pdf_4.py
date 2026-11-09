# 需要安装 reportlab 库: pip install reportlab
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from datetime import datetime

def create_xinjiang_travel_guide(filename="xinjiang_travel_guide.pdf"):
    """
    生成新疆旅游攻略PDF文件
    """
    # 创建PDF文档
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm
    )
    
    # 构建内容列表
    story = []
    
    # 定义样式
    styles = getSampleStyleSheet()
    
    # 自定义标题样式
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        leading=30,
        alignment=TA_CENTER,
        spaceAfter=20,
        textColor=colors.HexColor('#2C3E50')
    )
    
    # 自定义副标题样式
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Heading2'],
        fontSize=14,
        alignment=TA_CENTER,
        spaceAfter=15,
        textColor=colors.HexColor('#7F8C8D')
    )
    
    # 自定义段落样式
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        leading=16,
        alignment=TA_LEFT,
        spaceAfter=10
    )
    
    # 自定义小标题样式
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading3'],
        fontSize=14,
        leading=18,
        spaceBefore=15,
        spaceAfter=8,
        textColor=colors.HexColor('#2980B9')
    )
    
    # 封面页
    story.append(Spacer(1, 50*mm))
    story.append(Paragraph("新疆旅游攻略", title_style))
    story.append(Spacer(1, 10*mm))
    story.append(Paragraph("探索大美新疆，感受丝路风情", subtitle_style))
    story.append(Spacer(1, 10*mm))
    story.append(Paragraph(f"生成日期: {datetime.now().strftime('%Y年%m月%d日')}", normal_style))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("────────────────────────────────", normal_style))
    story.append(PageBreak())
    
    # 目录页
    story.append(Paragraph("目录", title_style))
    story.append(Spacer(1, 10*mm))
    
    toc_items = [
        "一、新疆概况",
        "二、最佳旅游时间",
        "三、主要旅游景点",
        "四、交通指南",
        "五、美食推荐",
        "六、住宿建议",
        "七、注意事项",
        "八、行程推荐"
    ]
    
    for item in toc_items:
        toc_style = ParagraphStyle(
            'TOCStyle',
            parent=styles['Normal'],
            fontSize=12,
            leading=20,
            leftIndent=20,
            textColor=colors.HexColor('#34495E')
        )
        story.append(Paragraph(item, toc_style))
    
    story.append(PageBreak())
    
    # 一、新疆概况
    story.append(Paragraph("一、新疆概况", heading_style))
    story.append(Paragraph(
        "新疆维吾尔自治区，简称新，位于中国西北部，是中国陆地面积最大的省级行政区。"
        "新疆总面积约166万平方公里，占中国国土总面积的六分之一。这里拥有壮丽的自然风光、"
        "丰富的历史文化和多样的民族风情，是丝绸之路的重要通道，也是东西方文明交汇的地方。"
        "新疆地形格局为\"三山夹两盆\"，北部为阿尔泰山，中部为天山，南部为昆仑山；"
        "天山以北为准噶尔盆地，天山以南为塔里木盆地。",
        normal_style
    ))
    
    story.append(Paragraph(
        "新疆共有47个民族成分，其中维吾尔族、汉族、哈萨克族、回族、柯尔克孜族等为主要民族。"
        "多元文化交融，形成了独特的新疆文化魅力。",
        normal_style
    ))
    
    # 二、最佳旅游时间
    story.append(Paragraph("二、最佳旅游时间", heading_style))
    story.append(Paragraph("新疆地域辽阔，不同地区最佳旅游时间有所不同：", normal_style))
    
    time_data = [
        ["季节", "推荐区域", "特点"],
        ["春季(3-5月)", "伊犁河谷、天山天池", "杏花盛开、气候宜人"],
        ["夏季(6-8月)", "全境", "草原碧绿、瓜果飘香、避暑胜地"],
        ["秋季(9-10月)", "喀纳斯、吐鲁番", "金黄胡杨、丰收季节、色彩斑斓"],
        ["冬季(11-2月)", "阿勒泰、乌鲁木齐", "冰雪旅游、滑雪胜地"]
    ]
    
    time_table = Table(time_data, colWidths=[40*mm, 50*mm, 60*mm])
    time_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498DB')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ECF0F1')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#BDC3C7')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F9FA')]),
    ]))
    story.append(time_table)
    story.append(Spacer(1, 10*mm))
    
    # 三、主要旅游景点
    story.append(Paragraph("三、主要旅游景点", heading_style))
    
    story.append(Paragraph("3.1 北疆景点", heading_style))
    story.append(Paragraph(
        "• 喀纳斯湖：位于阿勒泰地区布尔津县，被誉为\"人间仙境\"、\"神的后花园\"。"
        "湖水颜色随季节变化，周围原始森林和图瓦人村落构成绝美风景。",
        normal_style
    ))
    story.append(Paragraph(
        "• 禾木村：中国最美六大古镇古村之一，图瓦人聚居地，晨雾中的小木屋如梦似幻。",
        normal_style
    ))
    story.append(Paragraph(
        "• 那拉提草原：世界四大草原之一，空中草原景色壮观，夏季绿草如茵、牛羊成群。",
        normal_style
    ))
    story.append(Paragraph(
        "• 赛里木湖：新疆海拔最高、面积最大的高山湖泊，被称为\"大西洋最后一滴眼泪\"。",
        normal_style
    ))
    story.append(Paragraph(
        "• 天山天池：位于阜康市，是著名的高山湖泊，传说中西王母洗澡的地方。",
        normal_style
    ))
    
    story.append(Paragraph("3.2 南疆景点", heading_style))
    story.append(Paragraph(
        "• 塔克拉玛干沙漠：世界第二大流动沙漠，可体验沙漠越野、骑骆驼等刺激活动。",
        normal_style
    ))
    story.append(Paragraph(
        "• 喀什古城：中国保存最完整的绿洲城市，充满浓郁的维吾尔族风情，感受千年丝路文化。",
        normal_style
    ))
    story.append(Paragraph(
        "• 帕米尔高原：\"世界屋脊\"，慕士塔格峰、喀拉库勒湖、盘龙古道等绝美景观。",
        normal_style
    ))
    story.append(Paragraph(
        "• 火焰山：位于吐鲁番，因《西游记》而闻名，中国最热的地方之一。",
        normal_style
    ))
    story.append(Paragraph(
        "• 交河故城：世界上最大、最古老、保存最完好的生土建筑城市，丝绸之路上的重要遗址。",
        normal_style
    ))
    
    story.append(Paragraph("3.3 东疆景点", heading_style))
    story.append(Paragraph(
        "• 吐鲁番葡萄沟：中国葡萄之乡，夏季葡萄成熟，可体验采摘乐趣。",
        normal_style
    ))
    story.append(Paragraph(
        "• 坎儿井：古代地下水利工程奇迹，与万里长城、京杭大运河并称为中国古代三大工程。",
        normal_style
    ))
    
    story.append(PageBreak())
    
    # 四、交通指南
    story.append(Paragraph("四、交通指南", heading_style))
    story.append(Paragraph("4.1 大交通", normal_style))
    story.append(Paragraph(
        "✈️ 飞机：乌鲁木齐地窝堡国际机场是新疆最大的航空枢纽，连接国内主要城市。"
        "北疆可飞喀纳斯机场、伊宁机场；南疆可飞喀什机场、和田机场。",
        normal_style
    ))
    story.append(Paragraph(
        "🚄 火车：乌鲁木齐是新疆铁路枢纽，兰新铁路连接内地。南疆铁路通往喀什。"
        "新疆火车旅行是一种独特的体验，可欣赏沿途风光。",
        normal_style
    ))
    story.append(Paragraph(
        "🚌 长途汽车：新疆各地州首府之间均有长途汽车连接，适合预算有限的旅行者。",
        normal_style
    ))
    
    story.append(Paragraph("4.2 当地交通", normal_style))
    story.append(Paragraph(
        "• 自驾：新疆路况整体较好，但距离遥远，建议经验丰富者自驾，注意加油和休息。"
        "推荐路线：乌鲁木齐-赛里木湖-伊宁-昭苏-特克斯-喀纳斯。",
        normal_style
    ))
    story.append(Paragraph(
        "• 包车：推荐选择当地司机包车，熟悉路况和景点，省心省力。",
        normal_style
    ))
    story.append(Paragraph(
        "• 公共交通：乌鲁木齐、喀什、伊犁等地有市内公交和出租车。",
        normal_style
    ))
    
    story.append(PageBreak())
    
    # 五、美食推荐
    story.append(Paragraph("五、美食推荐", heading_style))
    
    food_items = [
        ["美食名称", "特色描述", "推荐地点"],
        ["大盘鸡", "鸡肉与土豆炖煮，配以宽面，分量足味道香", "乌鲁木齐、喀什"],
        ["烤羊肉串", "鲜嫩多汁，孜然香辣，新疆最具代表性美食", "各地夜市"],
        ["手抓饭", "米饭与羊肉、胡萝卜、洋葱同煮，营养丰富", "全疆各地"],
        ["烤包子", "外皮酥脆，内馅羊肉洋葱，香气扑鼻", "喀什、乌鲁木齐"],
        ["拉条子", "手工拉面配以菜码和肉酱，筋道爽口", "全疆各地"],
        ["馕", "新疆主食，种类多样，可保存数天", "全疆各地"],
        ["酸奶", "浓郁醇厚，可添加蜂蜜或果酱", "全疆各地"],
        ["哈密瓜", "香甜多汁，被誉为\"瓜中之王\"", "哈密地区"],
        ["葡萄干", "品种繁多，无核白葡萄干最为著名", "吐鲁番"],
        ["抓饭", "米饭与胡萝卜、羊肉炖煮，香气四溢", "喀什、和田"]
    ]
    
    food_table = Table(food_items, colWidths=[35*mm, 75*mm, 40*mm])
    food_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E67E22')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FDF2E9')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#F0B27A')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FDEBD0')]),
    ]))
    story.append(food_table)
    
    story.append(Spacer(1, 10*mm))
    story.append(Paragraph("💡 提示：新疆美食口味偏重，喜欢清淡口味的朋友可提前告知厨师。", normal_style))
    
    # 六、住宿建议
    story.append(Paragraph("六、住宿建议", heading_style))
    story.append(Paragraph(
        "新疆住宿选择丰富，从高端酒店到特色民宿应有尽有：",
        normal_style
    ))
    story.append(
        Paragraph("• 乌鲁木齐：高端酒店集中地，推荐国际连锁品牌如希尔顿、万豪等。", normal_style)
    )
    story.append(
        Paragraph("• 喀什古城：推荐特色民宿，体验维吾尔族传统建筑风格。", normal_style)
    )
    story.append(
        Paragraph("• 喀纳斯/禾木：推荐景区内小木屋或蒙古包，清晨推窗即见美景。", normal_style)
    )
    story.append(
        Paragraph("• 草原地区：夏季可体验哈萨克族毡房，感受游牧文化。", normal_style)
    )
    story.append(
        Paragraph("• 沙漠地区：部分沙漠景区提供帐篷酒店，体验星空露营。", normal_style)
    )
    story.append(Paragraph("💡 提示：旺季(6-8月、9-10月)需提前预订住宿，价格会上涨30%-50%。", normal_style))
    
    story.append(PageBreak())
    
    # 七、注意事项
    story.append(Paragraph("七、注意事项", heading_style))
    
    notes = [
        "1. 身份证件：新疆安检严格，随身携带身份证，部分边境地区需办理边防证。",
        "2. 气候干燥：新疆气候干燥，注意补水保湿，准备润唇膏和保湿护肤品。",
        "3. 时差：新疆使用北京时间，但实际日出日落时间比内地晚2小时左右。",
        "4. 尊重习俗：尊重当地少数民族风俗习惯，进入清真寺需脱鞋，注意着装得体。",
        "5. 饮食习惯：清真餐厅不猪肉，点餐时注意区分。",
        "6. 防晒措施：新疆紫外线强，备好防晒霜、太阳镜、遮阳帽。",
        "7. 安全第一：自驾注意路况，避免夜间行车；参加高风险活动选择正规机构。",
        "8. 网络信号：部分偏远地区信号较弱，提前下载离线地图。",
        "9. 现金准备：部分偏远地区信号不好，建议携带适量现金。",
        "10. 环保出行：保护自然环境，不乱扔垃圾，尊重野生动物。"
    ]
    
    for note in notes:
        story.append(Paragraph(note, normal_style))
    
    story.append(Spacer(1, 15*mm))
    
    # 八、行程推荐
    story.append(Paragraph("八、行程推荐", heading_style))
    
    story.append(Paragraph("8.1 经典北疆7日游", heading_style))
    story.append(Paragraph(
        "D1: 乌鲁木齐-赛里木湖-伊宁<br>"
        "D2: 伊宁-昭苏-特克斯<br>"
        "D3: 特克斯-喀拉峻草原<br>"
        "D4: 喀拉峻-巩乃斯林场<br>"
        "D5: 巩乃斯-巴音布鲁克<br>"
        "D6: 巴音布鲁克-独山子大峡谷<br>"
        "D7: 独山子-乌鲁木齐<br>"
        "<br>特点：草原风光、高山湖泊、峡谷地貌",
        normal_style
    ))
    
    story.append(Paragraph("8.2 北疆喀纳斯6日游", heading_style))
    story.append(Paragraph(
        "D1: 乌鲁木齐-布尔津<br>"
        "D2: 布尔津-喀纳斯<br>"
        "D3: 喀纳斯深度游(三湾徒步)<br>"
        "D4: 喀纳斯-禾木<br>"
        "D5: 禾木-布尔津<br>"
        "D6: 布尔津-乌鲁木齐<br>"
        "<br>特点：原始森林、图瓦村落、晨雾美景",
        normal_style
    ))
    
    story.append(Paragraph("8.3 南疆文化5日游", heading_style))
    story.append(Paragraph(
        "D1: 乌鲁木齐-喀什<br>"
        "D2: 喀什古城-艾提尕尔清真寺<br>"
        "D3: 喀什-白沙湖-卡拉库勒湖<br>"
        "D4: 卡拉库勒湖-慕士塔格峰-红其拉甫<br>"
        "D5: 喀什-乌鲁木齐<br>"
        "<br>特点：丝路文化、帕米尔高原、边境风情",
        normal_style
    ))
    
    story.append(PageBreak())
    
    # 结语
    story.append(Paragraph("结语", title_style))
    story.append(Spacer(1, 15*mm))
    story.append(Paragraph(
        "新疆，一个让人来了就不想离开的地方。"
        "这里有大漠孤烟的壮阔，有长河落日的苍凉；"
        "有雪山冰川的圣洁，有草原牧歌的悠扬；"
        "有千年古堡的神秘，有丝路驼铃的回响。"
        "<br><br>"
        "无论你是热爱自然风光的户外爱好者，"
        "还是钟情历史文化的深度旅行者，"
        "新疆都能满足你的所有想象。"
        "<br><br>"
        "带上你的行囊，出发吧！"
        "新疆，等你来探索！",
        ParagraphStyle(
            'Conclusion',
            parent=normal_style,
            fontSize=12,
            leading=18,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#2C3E50')
        )
    ))
    story.append(Spacer(1, 20*mm))
    story.append(Paragraph("────────────────────────────────", normal_style))
    story.append(Paragraph("祝您旅途愉快！", normal_style))
    
    # 构建PDF
    doc.build(story)
    print(f"新疆旅游攻略PDF文件已生成: {filename}")
    return filename

if __name__ == "__main__":
    create_xinjiang_travel_guide()