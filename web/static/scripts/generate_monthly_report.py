from fpdf import FPDF
import os

def generate_monthly_report():
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
    else:
        # 如果没有找到中文字体，尝试添加一个备用方案或提示用户
        # 这里为了代码健壮性，如果找不到字体，我们设置默认Arial，但中文会乱码
        pass

    font_name = 'ChineseFont' if font_path else 'Arial'

    # 设置标题
    pdf.set_font(font_name, '', 18)
    pdf.cell(0, 20, '月度报告', ln=True, align='C')
    pdf.ln(10)

    # 设置正文
    pdf.set_font(font_name, '', 12)
    
    # 正文内容
    content = [
        "本月销售情况分析",
        "",
        "1. 总体销售数据：",
        "   本月总销售额为 150,000 元，较上月增长 12%。",
        "   总订单数量为 1,200 单，平均客单价为 125 元。",
        "",
        "2. 主要产品销售表现：",
        "   - A类产品：销售额 80,000 元，占比 53.3%，表现强劲。",
        "   - B类产品：销售额 50,000 元，占比 33.3%，保持稳定。",
        "   - C类产品：销售额 20,000 元，占比 13.4%，略有下滑，需关注。",
        "",
        "3. 区域销售分布：",
        "   - 华东地区：销售额 60,000 元，占比最高。",
        "   - 华南地区：销售额 45,000 元，位居第二。",
        "   - 华北地区：销售额 30,000 元。",
        "   - 其他地区：销售额 15,000 元。",
        "",
        "4. 问题与挑战：",
        "   - C类产品库存积压严重，建议下月开展促销活动。",
        "   - 华南地区新市场拓展进度缓慢，需加强地推力度。",
        "",
        "5. 下月计划：",
        "   - 推出C类产品限时折扣活动，目标清理库存30%。",
        "   - 针对华南地区制定专项市场推广方案。",
        "   - 优化A类产品供应链，确保爆款不断货。",
        "",
        "报告生成日期：2023年10月"
    ]

    for line in content:
        pdf.multi_cell(0, 10, line)
        pdf.ln(2)  # 每段之间增加一点间距

    # 保存文件
    pdf.output('monthly_report.pdf')
    print("PDF已生成: monthly_report.pdf")

if __name__ == "__main__":
    generate_monthly_report()