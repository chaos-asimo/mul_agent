import os
import tempfile
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT

def generate_xinjiang_travel_guide(filename="xinjiang_travel_guide.pdf"):
    """
    Generates a PDF travel guide for Xinjiang.
    Since we cannot directly provide a downloadable file link in a console script,
    this script creates a PDF file and prints its local path.
    """
    
    # Create a temporary directory to store the file
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, filename)

    # Create the PDF document
    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm
    )

    # Define styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        alignment=TA_CENTER,
        spaceAfter=12*mm,
        textColor=colors.HexColor('#2E8B57')  # SeaGreen
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=14,
        alignment=TA_CENTER,
        spaceAfter=6*mm,
        textColor=colors.HexColor('#555555')
    )
    
    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Heading2'],
        fontSize=16,
        spaceBefore=6*mm,
        spaceAfter=3*mm,
        textColor=colors.HexColor('#2F4F4F')  # DarkSlateGray
    )
    
    content_style = ParagraphStyle(
        'CustomContent',
        parent=styles['Normal'],
        fontSize=12,
        leading=16,
        alignment=TA_LEFT
    )

    # Content
    elements = []

    # Title Section
    elements.append(Paragraph("新疆旅游攻略<br/>Xinjiang Travel Guide", title_style))
    elements.append(Paragraph("大漠孤烟直，长河落日圆", subtitle_style))
    elements.append(Spacer(1, 6*mm))

    # Introduction
    elements.append(Paragraph("1. 简介", header_style))
    elements.append(Paragraph(
        "新疆维吾尔自治区（简称‘新’）位于中国西北边陲，面积166万平方公里，"
        "是中国陆地面积最大的省级行政区。这里风景壮丽，民族风情浓郁，"
        "拥有独特的地理风貌和深厚的历史文化底蕴。从雪山草原到沙漠绿洲，"
        "从喀纳斯的童话世界到吐鲁番的火洲，每一步都是风景。",
        content_style
    ))
    elements.append(Spacer(1, 4*mm))

    # Best Time to Visit
    elements.append(Paragraph("2. 最佳旅行时间", header_style))
    elements.append(Paragraph(
        "新疆地域辽阔，不同地区最佳旅行时间略有差异：<br/>"
        "<b>北疆（阿勒泰、伊犁）：</b> 5月-10月。<br/>"
        "&nbsp;&nbsp;- 5-6月：鲜花盛开，草原碧绿。<br/>"
        "&nbsp;&nbsp;- 9-10月：秋景绝美，层林尽染。<br/>"
        "<b>南疆（喀什、和田）：</b> 9月-次年5月。<br/>"
        "&nbsp;&nbsp;- 春秋季节气候宜人，适合人文探索。<br/>"
        "<b>天山天池/乌鲁木齐周边：</b> 全年皆宜，夏季避暑，冬季滑雪。",
        content_style
    ))
    elements.append(Spacer(1, 4*mm))

    # Itinerary Suggestion
    elements.append(Paragraph("3. 经典路线推荐：北疆环线10日", header_style))
    
    itinerary_data = [
        [Paragraph('<b>天数</b>', content_style), Paragraph('<b>景点</b>', content_style), Paragraph('<b>亮点</b>', content_style)],
        [Paragraph('Day 1', content_style), Paragraph('乌鲁木齐', content_style), Paragraph('博物馆、大巴扎', content_style)],
        [Paragraph('Day 2', content_style), Paragraph('乌鲁木齐 - 赛里木湖', content_style), Paragraph('大西洋最后一滴眼泪', content_style)],
        [Paragraph('Day 3', content_style), Paragraph('赛里木湖 - 伊宁', content_style), Paragraph('薰衣草、六星街', content_style)],
        [Paragraph('Day 4', content_style), Paragraph('伊宁 - 独库公路北段', content_style), Paragraph('一日四季，十里不同天', content_style)],
        [Paragraph('Day 5', content_style), Paragraph('乔尔玛 - 那拉提', content_style), Paragraph('空中草原', content_style)],
        [Paragraph('Day 6', content_style), Paragraph('那拉提 - 巴音布鲁克', content_style), Paragraph('九曲十八弯日落', content_style)],
        [Paragraph('Day 7', content_style), Paragraph('巴音布鲁克 - 乌鲁木齐', content_style), Paragraph('穿越南段，返回古城', content_style)],
        [Paragraph('Day 8', content_style), Paragraph('乌鲁木齐 - 可可托海', content_style), Paragraph('额尔齐斯大峡谷', content_style)],
        [Paragraph('Day 9', content_style), Paragraph('可可托海 - 喀纳斯', content_style), Paragraph('神的后花园', content_style)],
        [Paragraph('Day 10', content_style), Paragraph('喀纳斯 - 乌鲁木齐', content_style), Paragraph('三湾徒步，返程', content_style)]
    ]

    table = Table(itinerary_data, colWidths=[30*mm, 60*mm, 100*mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E8B57')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 6*mm))

    # Food Recommendations
    elements.append(Paragraph("4. 美食推荐", header_style))
    elements.append(Paragraph(
        "新疆美食以牛羊肉、面食和水果闻名。<br/>"
        "• <b>烤羊肉串</b>：外焦里嫩，香气四溢。<br/>"
        "• <b>大盘鸡</b>：土豆与鸡肉的完美搭配，配以皮带面。<br/>"
        "• <b>手抓饭</b>：胡萝卜、羊肉与米饭的经典组合。<br/>"
        "• <b>拉条子</b>：劲道十足的手工拌面。<br/>"
        "• <b>烤包子 & 馕坑肉</b>：传统西域风味。<br/>"
        "• <b>瓜果</b>：哈密瓜、葡萄、石榴、无花果等。",
        content_style
    ))
    elements.append(Spacer(1, 6*mm))

    # Tips
    elements.append(Paragraph("5. 旅行贴士", header_style))
    elements.append(Paragraph(
        "1. <b>气候</b>：新疆昼夜温差大，即使是夏季也要带一件外套。气候干燥，注意补水保湿。<br/>"
        "2. <b>时差</b>：新疆使用北京时间，但实际作息比内地晚2小时左右（通常10点上班，22点天黑）。<br/>"
        "3. <b>交通</b>：景点之间距离遥远，建议自驾或包车，提前规划路线。<br/>"
        "4. <b>证件</b>：部分边境地区需要办理边防证。<br/>"
        "5. <b>尊重</b>：尊重当地少数民族的风俗习惯和宗教信仰。",
        content_style
    ))

    # Build PDF
    doc.build(elements)
    print(f"PDF generated successfully: {file_path}")
    return file_path

if __name__ == "__main__":
    generate_xinjiang_travel_guide()