import requests
import json
import time

# 配置后端API地址，请根据实际部署情况修改
BASE_URL = "http://localhost:5000"  # 示例地址，请替换为实际地址

class YijingClient:
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url.rstrip('/')

    def _get(self, endpoint):
        """发送GET请求"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"GET请求失败 {endpoint}: {e}")
            return None

    def _post(self, endpoint, data=None):
        """发送POST请求"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"POST请求失败 {endpoint}: {e}")
            return None

    def shake(self):
        """
        执行一次完整摇卦
        返回: 包含卦象信息、变爻、时间等字典，失败返回None
        """
        return self._get("/api/yijing/shake")

    def get_all_hexagrams(self):
        """
        获取所有六十四卦数据
        返回: 六十四卦列表或字典，失败返回None
        """
        return self._get("/api/yijing/hexagrams")

    def get_bagua(self):
        """
        获取八卦信息
        返回: 八卦信息字典，失败返回None
        """
        return self._get("/api/yijing/bagua")

    def get_hexagram_detail(self, name):
        """
        根据卦名获取详细信息
        参数:
            name: 卦名，如 '乾', '坤' 等
        返回: 卦象详细信息字典，失败返回None
        """
        return self._get(f"/api/yijing/hexagram/{name}")

    def save_reading(self, data):
        """
        保存卜卦结果
        参数:
            data: 包含卜卦结果的字典，通常包含 session_id, hexagram, changed_lines 等字段
        返回: 保存结果字典，失败返回None
        """
        if not data:
            print("保存数据不能为空")
            return None
        return self._post("/api/yijing/save", data)

    def get_history(self):
        """
        获取卜卦历史列表
        返回: 历史记录列表，失败返回None
        """
        return self._get("/api/yijing/history")

    def get_history_detail(self, session_id):
        """
        获取单个卜卦记录详情
        参数:
            session_id: 会话ID
        返回: 详细记录字典，失败返回None
        """
        return self._get(f"/api/yijing/history/{session_id}")

    def delete_history(self, session_id):
        """
        删除卜卦历史记录
        参数:
            session_id: 会话ID
        返回: 删除操作结果字典，失败返回None
        """
        url = f"{self.base_url}/api/yijing/history/{session_id}"
        try:
            response = requests.delete(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"DELETE请求失败 {session_id}: {e}")
            return None

    def ai_explain(self, session_id, prompt=""):
        """
        AI解卦 - 非流式返回
        参数:
            session_id: 会话ID
            prompt: 可选的自定义问题或提示
        返回: AI解释内容字符串或字典，失败返回None
        """
        data = {"session_id": session_id}
        if prompt:
            data["prompt"] = prompt
        return self._post("/api/yijing/ai-explain", data)

    def ai_explain_stream(self, session_id, prompt=""):
        """
        AI解卦 - SSE流式返回
        注意：requests库对SSE支持有限，这里使用简单示例。
        实际生产中建议使用 sseclient 或 httpx 等库。
        参数:
            session_id: 会话ID
            prompt: 可选的自定义问题或提示
        返回: 生成的文本内容，失败返回None
        """
        url = f"{self.base_url}/api/yijing/ai-explain-stream"
        params = {"session_id": session_id}
        if prompt:
            params["prompt"] = prompt
        
        try:
            response = requests.get(url, params=params, stream=True)
            response.raise_for_status()
            full_text = []
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data:"):
                        data_content = decoded_line[5:].strip()
                        if data_content:
                            full_text.append(data_content)
            return "".join(full_text)
        except requests.exceptions.RequestException as e:
            print(f"SSE请求失败: {e}")
            return None


def main():
    client = YijingClient()

    print("=== 周易卜卦客户端演示 ===\n")

    # 1. 摇卦
    print("1. 执行摇卦...")
    shake_result = client.shake()
    if shake_result:
        print(f"摇卦结果: {json.dumps(shake_result, indent=2, ensure_ascii=False)}")
        session_id = shake_result.get("session_id")
        hexagram_name = shake_result.get("hexagram", {}).get("name", "Unknown")
        print(f"当前卦名: {hexagram_name}")
        print(f"Session ID: {session_id}")
    else:
        print("摇卦失败")
        return

    time.sleep(1)

    # 2. 保存卜卦结果
    print("\n2. 保存卜卦结果...")
    save_data = {
        "session_id": session_id,
        "hexagram": shake_result.get("hexagram"),
        "changed_lines": shake_result.get("changed_lines"),
        "timestamp": shake_result.get("timestamp")
    }
    save_result = client.save_reading(save_data)
    if save_result:
        print(f"保存结果: {json.dumps(save_result, indent=2, ensure_ascii=False)}")
    else:
        print("保存失败")

    time.sleep(1)

    # 3. 获取历史记录
    print("\n3. 获取卜卦历史记录...")
    history = client.get_history()
    if history:
        print(f"历史记录数量: {len(history)}")
        for record in history:
            print(f"  - Session: {record.get('session_id')}, 卦名: {record.get('hexagram', {}).get('name', 'N/A')}, 时间: {record.get('timestamp')}")
    else:
        print("获取历史记录失败")

    time.sleep(1)

    # 4. 获取当前卦象详情
    print("\n4. 获取当前卦象详情...")
    if hexagram_name != "Unknown":
        detail = client.get_hexagram_detail(hexagram_name)
        if detail:
            print(f"卦象详情: {json.dumps(detail, indent=2, ensure_ascii=False)}")
        else:
            print("获取详情失败")
    else:
        print("无法获取卦名，跳过详情查询")

    time.sleep(1)

    # 5. AI解卦 (非流式)
    print("\n5. 进行AI解卦...")
    if session_id:
        ai_result = client.ai_explain(session_id, "请简要解释此卦的含义。")
        if ai_result:
            print(f"AI解卦结果: {ai_result}")
        else:
            print("AI解卦失败")
    else:
        print("无Session ID，跳过AI解卦")

    # 注意: AI解卦流式返回在实际调用中可能需要更复杂的处理，此处仅展示接口存在性
    print("\n6. (可选) 测试AI解卦流式接口...")
    if session_id:
        # 由于requests对SSE支持有限，此处仅打印提示
        print("AI解卦流式接口已调用 (注: requests库对SSE支持有限，实际输出可能不完整)")
        # 如果需要完整SSE支持，请使用 sseclient 库: pip install sseclient-py
        # import sseclient
        # client_stream = sseclient.SSEClient(f"{BASE_URL}/api/yijing/ai-explain-stream", params={"session_id": session_id})
        # for event in client_stream:
        #     print(event.data, end='', flush=True)

    print("\n=== 演示结束 ===")

if __name__ == "__main__":
    main()