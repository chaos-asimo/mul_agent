import os
from fpdf import FPDF

def generate_pdf(filename="xinjiang_travel_guide.pdf"):
    """
    生成新疆旅游攻略PDF文件
    """
    # 检查是否安装了fpdf库，如果未安装需要运行: pip install fpdf
    try:
        from fpdf import FPDF
    except ImportError:
        print("错误: 需要安装 fpdf 库。请运行 'pip install fpdf'")
        return

    pdf = FPDF()
    pdf.add_page()
    
    # 设置字体
    pdf.set_font("Arial", size=12)
    
    # 添加标题
    pdf.set_font("Arial", style='B', size=16)
    pdf.cell(200, 10, txt="新疆旅游攻略", ln=True, align='C')
    pdf.ln(10)
    
    # 添加正文内容
    pdf.set_font("Arial", size=12)
    
    content = [
        ("一、最佳旅行时间", 
         "新疆地域辽阔，四季景色各异。5-10月是最佳旅游季节，特别是6-9月，气候适宜，风景最美。"),
        
        ("二、主要景点推荐", 
         "1. 喀纳斯湖：位于阿勒泰地区，被誉为'人间仙境'\n"
         "2. 天山天池：世界自然遗产，高山湖泊美景\n"
         "3. 吐鲁番火焰山：独特的丹霞地貌\n"
         "4. 喀什古城：感受浓郁的维吾尔族风情\n"
         "5. 那拉提草原：空中草原，风光旖旎"),
        
        ("三、交通指南", 
         "1. 飞机：乌鲁木齐地窝堡国际机场是主要门户\n"
         "2. 火车：兰新铁路连接内地主要城市\n"
         "3. 自驾：新疆公路网络发达，适合自驾游\n"
         "4. 包车：建议聘请当地导游，了解路况和习俗"),
        
        ("四、美食推荐", 
         "1. 烤羊肉串：新疆最具代表性的美食\n"
         "2. 大盘鸡：鸡肉与土豆的完美组合\n"
         "3. 抓饭：米饭、羊肉、胡萝卜的混合盛宴\n"
         "4. 馕饼：新疆人的主食，种类繁多\n"
         "5. 葡萄干：吐鲁番特产，甜度极高"),
        
        ("五、注意事项", 
         "1. 新疆昼夜温差大，注意添减衣物\n"
         "2. 尊重当地民族风俗和宗教信仰\n"
         "3. 携带防晒霜、墨镜等防晒用品\n"
         "4. 准备充足的饮用水\n"
         "5. 提前了解景区开放时间和门票信息"),
        
        ("六、行程建议", 
         "7-10天行程推荐：\n"
         "Day 1-2: 乌鲁木齐市区游览\n"
         "Day 3-4: 天山天池、吐鲁番\n"
         "Day 5-7: 喀纳斯、禾木村\n"
         "Day 8-9: 伊犁河谷、那拉提草原\n"
         "Day 10: 喀什古城、返程")
    ]
    
    for title, text in content:
        pdf.set_font("Arial", style='B', size=12)
        pdf.cell(200, 10, txt=title, ln=True)
        pdf.set_font("Arial", size=12)
        for line in text.split('\n'):
            pdf.multi_cell(0, 10, txt=line)
        pdf.ln(5)
    
    # 保存文件
    pdf.output(filename)
    print(f"新疆旅游攻略已生成: {os.path.abspath(filename)}")
    print(f"文件大小: {os.path.getsize(filename)} 字节")

if __name__ == "__main__":
    generate_pdf()