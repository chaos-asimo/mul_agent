import random
from .hexagrams import BA_GUA, LIU_SHI_SI_GUA_MATRIX, YAO_NAMES, get_hexagram_by_index, get_yao_text, get_extra_text

class YaoResult:
    def __init__(self, position: int, coin_result: str, value: int, yao_type: str, is_yang: bool, is_change: bool):
        self.position = position
        self.name = YAO_NAMES[position - 1]
        self.coin_result = coin_result
        self.value = value
        self.type = yao_type
        self.is_yang = is_yang
        self.is_change = is_change

    def to_dict(self):
        return {
            "position": self.position,
            "name": self.name,
            "coin_result": self.coin_result,
            "value": self.value,
            "type": self.type,
            "is_yang": self.is_yang,
            "is_change": self.is_change
        }

class HexagramResult:
    def __init__(self):
        self.original_hexagram = None
        self.changed_hexagram = None
        self.yao_results = []
        self.change_count = 0
        self.solution_text = ""
        self.change_yao_positions = []

    def to_dict(self):
        return {
            "original_hexagram": self.original_hexagram,
            "changed_hexagram": self.changed_hexagram,
            "yao_results": [y.to_dict() for y in self.yao_results],
            "change_count": self.change_count,
            "solution_text": self.solution_text,
            "change_yao_positions": self.change_yao_positions
        }

class YijingDivination:
    @staticmethod
    def shake_coin() -> bool:
        return random.choice([True, False])

    @staticmethod
    def shake_once() -> dict:
        backs = sum([1 for _ in range(3) if YijingDivination.shake_coin()])
        if backs == 3:
            return {
                "backs": 3,
                "value": 9,
                "type": "老阳",
                "is_yang": True,
                "is_change": True,
                "coin_result": "三背"
            }
        elif backs == 2:
            return {
                "backs": 2,
                "value": 8,
                "type": "少阴",
                "is_yang": False,
                "is_change": False,
                "coin_result": "两背一字"
            }
        elif backs == 1:
            return {
                "backs": 1,
                "value": 7,
                "type": "少阳",
                "is_yang": True,
                "is_change": False,
                "coin_result": "两字一背"
            }
        else:
            return {
                "backs": 0,
                "value": 6,
                "type": "老阴",
                "is_yang": False,
                "is_change": True,
                "coin_result": "三字"
            }

    @staticmethod
    def divinate() -> HexagramResult:
        result = HexagramResult()
        yao_results = []
        
        for i in range(1, 7):
            shake_result = YijingDivination.shake_once()
            yao = YaoResult(
                position=i,
                coin_result=shake_result["coin_result"],
                value=shake_result["value"],
                yao_type=shake_result["type"],
                is_yang=shake_result["is_yang"],
                is_change=shake_result["is_change"]
            )
            yao_results.append(yao)
        
        result.yao_results = yao_results
        
        original_yao = [y.is_yang for y in yao_results]
        result.change_count = sum(1 for y in yao_results if y.is_change)
        result.change_yao_positions = [y.position for y in yao_results if y.is_change]
        
        changed_yao = []
        for y in yao_results:
            if y.is_change:
                changed_yao.append(not y.is_yang)
            else:
                changed_yao.append(y.is_yang)
        
        lower_gua_original = original_yao[:3]
        upper_gua_original = original_yao[3:]
        
        lower_row = YijingDivination._find_gua_index(lower_gua_original)
        upper_col = YijingDivination._find_gua_index(upper_gua_original)
        
        result.original_hexagram = get_hexagram_by_index(lower_row, upper_col)
        
        if result.change_count > 0:
            lower_gua_changed = changed_yao[:3]
            upper_gua_changed = changed_yao[3:]
            
            lower_row_changed = YijingDivination._find_gua_index(lower_gua_changed)
            upper_col_changed = YijingDivination._find_gua_index(upper_gua_changed)
            
            result.changed_hexagram = get_hexagram_by_index(lower_row_changed, upper_col_changed)
        
        result.solution_text = YijingDivination._generate_solution(result)
        
        return result

    @staticmethod
    def _find_gua_index(yao_list: list) -> int:
        for i, gua in enumerate(BA_GUA):
            if gua["yao"] == yao_list:
                return i
        return 0

    @staticmethod
    def _generate_solution(result: HexagramResult) -> str:
        lines = []
        
        if result.change_count == 0:
            lines.append("【解卦】")
            lines.append(f"变爻数：0")
            lines.append(f"解卦方法：看本卦卦辞")
            lines.append(f"本卦：{result.original_hexagram['full_name']}")
            lines.append(f"卦辞：{result.original_hexagram['description']}")
            lines.append("")
            lines.append("【卦义解读】")
            lines.append("当前卦象稳定，无明显变化趋势，宜守正持恒，静观其变。")
        elif result.change_count == 1:
            lines.append("【解卦】")
            lines.append(f"变爻数：1")
            lines.append(f"解卦方法：重点看变爻爻辞")
            lines.append(f"本卦：{result.original_hexagram['full_name']}")
            lines.append(f"之卦：{result.changed_hexagram['full_name'] if result.changed_hexagram else ''}")
            lines.append("")
            lines.append("【变爻详解】")
            for pos in result.change_yao_positions:
                yao_text = get_yao_text(result.original_hexagram['name'], pos)
                if yao_text:
                    lines.append(f"第{pos}爻（{YAO_NAMES[pos-1]}）：{yao_text}")
                else:
                    lines.append(f"第{pos}爻（{YAO_NAMES[pos-1]}）：爻辞暂缺")
            lines.append("")
            lines.append("【卦义解读】")
            lines.append("变化的关键在此一爻，此爻的动向将决定事情的发展方向。")
        elif result.change_count == 2:
            lines.append("【解卦】")
            lines.append(f"变爻数：2")
            lines.append(f"解卦方法：结合两爻爻辞与本卦")
            lines.append(f"本卦：{result.original_hexagram['full_name']}")
            lines.append(f"卦辞：{result.original_hexagram['description']}")
            lines.append(f"之卦：{result.changed_hexagram['full_name'] if result.changed_hexagram else ''}")
            lines.append("")
            lines.append("【变爻详解】")
            for pos in result.change_yao_positions:
                yao_text = get_yao_text(result.original_hexagram['name'], pos)
                if yao_text:
                    lines.append(f"第{pos}爻（{YAO_NAMES[pos-1]}）：{yao_text}")
                else:
                    lines.append(f"第{pos}爻（{YAO_NAMES[pos-1]}）：爻辞暂缺")
            lines.append("")
            lines.append("【卦义解读】")
            lines.append("两爻互动，需综合考虑两者的关系，平衡各方因素。")
        elif result.change_count == 3:
            lines.append("【解卦】")
            lines.append(f"变爻数：3")
            lines.append(f"解卦方法：看本卦与之卦卦辞综合")
            lines.append(f"本卦：{result.original_hexagram['full_name']}")
            lines.append(f"卦辞：{result.original_hexagram['description']}")
            lines.append(f"之卦：{result.changed_hexagram['full_name'] if result.changed_hexagram else ''}")
            if result.changed_hexagram:
                lines.append(f"之卦辞：{result.changed_hexagram['description']}")
            lines.append("")
            lines.append("【卦义解读】")
            lines.append("变化较大，需稳中求进，注意从本卦到之卦的转变过程。")
        elif result.change_count == 4:
            lines.append("【解卦】")
            lines.append(f"变爻数：4")
            lines.append(f"解卦方法：看之卦中未变的2个静爻")
            lines.append(f"本卦：{result.original_hexagram['full_name']}")
            lines.append(f"之卦：{result.changed_hexagram['full_name'] if result.changed_hexagram else ''}")
            lines.append("")
            lines.append("【静爻详解】")
            for y in result.yao_results:
                if not y.is_change:
                    yao_text = get_yao_text(result.original_hexagram['name'], y.position)
                    if yao_text:
                        lines.append(f"第{y.position}爻（{y.name}）：{yao_text}")
            lines.append("")
            lines.append("【卦义解读】")
            lines.append("大局要稳，重点关注不变的因素，以静制动。")
        elif result.change_count == 5:
            lines.append("【解卦】")
            lines.append(f"变爻数：5")
            lines.append(f"解卦方法：重点看唯一未变爻的爻辞")
            lines.append(f"本卦：{result.original_hexagram['full_name']}")
            lines.append(f"之卦：{result.changed_hexagram['full_name'] if result.changed_hexagram else ''}")
            lines.append("")
            lines.append("【静爻详解】")
            for y in result.yao_results:
                if not y.is_change:
                    yao_text = get_yao_text(result.original_hexagram['name'], y.position)
                    if yao_text:
                        lines.append(f"第{y.position}爻（{y.name}）：{yao_text}")
                    else:
                        lines.append(f"第{y.position}爻（{y.name}）：爻辞暂缺")
            lines.append("")
            lines.append("【卦义解读】")
            lines.append("唯一不变的爻是定盘星，以其为核心判断方向。")
        else:
            lines.append("【解卦】")
            lines.append(f"变爻数：6")
            lines.append(f"解卦方法：看之卦卦辞（乾坤用'用九/用六'）")
            lines.append(f"本卦：{result.original_hexagram['full_name']}")
            lines.append(f"之卦：{result.changed_hexagram['full_name'] if result.changed_hexagram else ''}")
            if result.changed_hexagram:
                lines.append(f"之卦辞：{result.changed_hexagram['description']}")
            lines.append("")
            extra_text = get_extra_text(result.original_hexagram['name'])
            if extra_text:
                lines.append(f"【特殊爻辞】")
                lines.append(extra_text)
            lines.append("")
            lines.append("【卦义解读】")
            lines.append("天地翻转，彻底变化，需顺应大势，把握机遇。")
        
        return "\n".join(lines)
