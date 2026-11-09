import random
import sys

# 定义八卦的基本属性
trigrams = {
    1: {"name": "乾", "element": "金", "nature": "天", "meaning": "开创、刚健"},
    2: {"name": "兑", "element": "金", "nature": "泽", "meaning": "喜悦、沟通"},
    3: {"name": "离", "element": "火", "nature": "火", "meaning": "光明、依附"},
    4: {"name": "震", "element": "木", "nature": "雷", "meaning": "震动、行动"},
    5: {"name": "巽", "element": "木", "nature": "风", "meaning": "顺从、渗透"},
    6: {"name": "坎", "element": "水", "nature": "水", "meaning": "险陷、智慧"},
    7: {"name": "艮", "element": "土", "nature": "山", "meaning": "静止、稳重"},
    8: {"name": "坤", "element": "土", "nature": "地", "meaning": "包容、顺承"}
}

# 定义六十四卦的简化解释 (这里仅列举部分典型卦象作为示例，实际应用中应包含全部64卦)
hexagram_meanings = {
    (1, 1): "乾为天: 元亨利贞。大吉，万事亨通，但需保持谦逊。",
    (8, 8): "坤为地: 元亨，利牝马之贞。大吉，顺势而为，厚德载物。",
    (1, 8): "天地否: 否之匪人。运势阻滞，宜守不宜进，等待时机。",
    (8, 1): "地天泰: 泰，小往大来。大吉，阴阳交感，通达顺畅。",
    (3, 7): "火山贲: 亨。小利有攸往。运势尚可，注重礼仪与装饰，低调行事。",
    (6, 4): "水雷屯: 元亨利贞。勿用有攸往。起始艰难，宜积蓄力量。",
    (4, 6): "山水蒙: 亨。匪我求童蒙，童蒙求我。运势不明，宜请教长者或专家。",
    (1, 4): "天雷无妄: 元亨利贞。其匪正有眚，不利有攸往。顺其自然，无妄之灾需防范。",
    (4, 1): "雷天大壮: 利贞。运势强盛，但不可恃强凌弱，需守正。",
    (6, 6): "坎为水: 习坎，有孚，维心亨。两险相重，需谨慎小心，保持内心坚定。",
    (3, 3): "离为火: 利贞，亨。畜牝牛，吉。光明相继，需依附正道，柔顺为佳。",
    (2, 2): "兑为泽: 亨，利贞。双喜临门，沟通顺畅，但需防口舌是非。",
    (5, 5): "巽为风: 小亨，利有攸往，利见大人。顺势而为，灵活应变。",
    (7, 7): "艮为山: 艮其背，不获其身。动静适时，宜静不宜动，止于至善。",
    # 默认通用解释，用于未列出的组合
    "default": "此卦象显示今日运势起伏不定，建议谨言慎行，保持平和心态，随机应变。"
}

def generate_hexagram():
    """
    模拟金钱卦起卦过程，生成上卦和下卦
    每次投掷三个硬币，正面为3，反面为2
    3个硬币之和可能为6(老阴), 7(少阳), 8(少阴), 9(老阳)
    这里简化处理，只取阴(偶数)阳(奇数)的二进制位来构建八卦
    实际上，易经起卦通常是从下往上画爻，共六次。
    为了简化脚本，我们直接随机生成两个八卦索引 (1-8)
    """
    upper_trigram_index = random.randint(1, 8)
    lower_trigram_index = random.randint(1, 8)
    return upper_trigram_index, lower_trigram_index

def get_daily_horoscope():
    """
    生成每日运程
    """
    print("=" * 40)
    print("       周易每日运程测算")
    print("=" * 40)
    
    # 获取当前日期作为种子，确保同一天结果一致 (可选，这里为了演示随机性，暂不设固定种子，
    # 若需每日固定，可使用 datetime.date.today() 作为 random.seed 的参数)
    # import datetime
    # random.seed(datetime.date.today())
    
    upper_idx, lower_idx = generate_hexagram()
    
    upper_tri = trigrams[upper_idx]
    lower_tri = trigrams[lower_idx]
    
    print(f"\n上卦: {upper_tri['name']} ({upper_tri['nature']}) - {upper_tri['meaning']}")
    print(f"下卦: {lower_tri['name']} ({lower_tri['nature']}) - {lower_tri['meaning']}")
    
    # 查找对应的六十四卦解释
    key = (upper_idx, lower_idx)
    if key in hexagram_meanings:
        interpretation = hexagram_meanings[key]
    else:
        # 如果字典中没有这个特定组合，生成一个基于元素的通用解释
        element_up = upper_tri['element']
        element_low = lower_tri['element']
        interpretation = f"上{upper_tri['name']}下{lower_tri['name']}。五行关系为{element_up}与{element_low}。"
        interpretation += " 运势提示：今日宜反思内心，调整状态，不可急躁。"
        
    print(f"\n【卦象解读】: {interpretation}")
    
    # 生成一个简易的运势评分 (1-10)
    # 这里使用简单的哈希逻辑或随机数，为了可重复性，可以基于卦象索引计算
    score = (upper_idx + lower_idx) % 10 + 1
    print(f"【今日运势评分】: {score}/10")
    
    if score >= 8:
        advice = "今日运势极佳，适合开展新项目、重要会议或社交活动。把握机会，勇往直前。"
    elif score >= 5:
        advice = "今日运势平稳，虽有小的波折，但整体可控。保持耐心，稳扎稳打即可。"
    else:
        advice = "今日运势稍弱，宜静守，不宜重大决策。多关注健康，避免冲突，以退为进。"
        
    print(f"【建议】: {advice}")
    print("=" * 40)

if __name__ == "__main__":
    try:
        get_daily_horoscope()
    except Exception as e:
        print(f"发生错误: {e}")
        sys.exit(1)