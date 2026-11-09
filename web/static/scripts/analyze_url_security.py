import requests
import urllib3
import json
import sys

# 禁用不安全请求警告（HTTPS证书验证警告）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def analyze_url_security(url):
    """
    分析URL的安全风险
    """
    risks = []
    findings = []

    # 1. 检查协议安全性
    if not url.startswith('https://'):
        risks.append("HIGH: URL使用HTTP而非HTTPS，数据传输未加密")
        findings.append("协议风险: 使用不安全的HTTP协议")
    else:
        findings.append("协议安全: 使用HTTPS协议")

    # 2. 检查URL结构
    if '$' in url:
        risks.append("MEDIUM: URL包含'$'字符，可能用于特殊查询参数或命令注入")
        findings.append("URL结构: 包含特殊字符'$'，需检查是否为合法查询参数")
    
    if 'm=' in url:
        findings.append("参数结构: 使用'm='作为方法标识，常见于RESTful API设计")

    # 3. 尝试访问URL检查基本响应
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        
        findings.append(f"响应状态码: {response.status_code}")
        
        # 检查常见安全头
        if 'X-Content-Type-Options' not in response.headers:
            risks.append("LOW: 缺少X-Content-Type-Options头")
        if 'X-Frame-Options' not in response.headers:
            risks.append("LOW: 缺少X-Frame-Options头")
        if 'Strict-Transport-Security' not in response.headers:
            risks.append("LOW: 缺少HSTS头")
            
        # 检查返回内容是否包含敏感信息
        try:
            data = response.json()
            if isinstance(data, dict):
                if any(key in str(data).lower() for key in ['password', 'secret', 'token', 'key']):
                    risks.append("CRITICAL: 响应中可能包含敏感信息")
        except:
            pass
            
    except requests.exceptions.RequestException as e:
        risks.append(f"CRITICAL: 无法连接到目标URL: {str(e)}")
        findings.append(f"连接错误: {str(e)}")

    # 4. 检查URL路径模式
    path_parts = url.split('/')[3] if len(url.split('/')) > 3 else ''
    if 'v2' in path_parts.lower():
        findings.append("版本信息: API使用v2版本")
    
    if 'query.service' in url:
        findings.append("服务类型: 查询服务接口")

    return {
        'url': url,
        'risks': risks,
        'findings': findings,
        'risk_count': len(risks)
    }

def main():
    target_url = "https://appsy.jbysoft.com/V2/PT/business/dealt/taskGroupV2$m=query.service"
    
    print("=" * 60)
    print("URL安全风险分析报告")
    print("=" * 60)
    print(f"\n目标URL: {target_url}")
    print("-" * 60)
    
    result = analyze_url_security(target_url)
    
    print("\n分析结果:")
    print("-" * 60)
    
    if result['findings']:
        print("\n【发现信息】")
        for finding in result['findings']:
            print(f"  • {finding}")
    
    if result['risks']:
        print("\n【安全风险】")
        for risk in result['risks']:
            print(f"  ⚠️  {risk}")
    else:
        print("\n✅ 未发现明显安全风险")
    
    print("-" * 60)
    print(f"\n风险等级: {'高危' if result['risk_count'] > 2 else '中危' if result['risk_count'] > 0 else '低风险'}")
    print(f"风险数量: {result['risk_count']}")
    print("\n建议:")
    print("  1. 确保使用HTTPS协议传输数据")
    print("  2. 验证API端点的身份认证机制")
    print("  3. 检查输入参数是否经过适当验证和过滤")
    print("  4. 确认API具有适当的速率限制")
    print("  5. 定期审查API访问日志")
    print("=" * 60)

if __name__ == "__main__":
    main()