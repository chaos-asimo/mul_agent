import os
import sys
import hashlib
import re
from pathlib import Path
from typing import List, Dict, Tuple

def calculate_file_hash(filepath: Path) -> str:
    """计算文件的SHA256哈希值"""
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except (IOError, PermissionError) as e:
        return f"Error: {e}"

def check_file_permissions(filepath: Path) -> List[str]:
    """检查文件权限潜在风险"""
    risks = []
    try:
        stat_info = filepath.stat()
        mode = stat_info.st_mode
        
        # 检查是否可执行且属于其他人
        if mode & 0o111 and not (mode & 0o011):
            risks.append(f"Executable by others: {filepath}")
        
        # 检查是否世界可写
        if mode & 0o002:
            risks.append(f"World-writable: {filepath}")
        
        # 检查是否有SUID/SGID位
        if mode & 0o4000:
            risks.append(f"SUID bit set: {filepath}")
        if mode & 0o2000:
            risks.append(f"SGID bit set: {filepath}")
            
    except (IOError, PermissionError) as e:
        risks.append(f"Permission error for {filepath}: {e}")
        
    return risks

def check_suspicious_patterns(filepath: Path) -> List[str]:
    """检查文件内容中的可疑模式"""
    risks = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        # 检查常见的恶意模式
        suspicious_patterns = [
            (r'eval\s*\(', 'Possible eval usage'),
            (r'exec\s*\(', 'Possible exec usage'),
            (r'subprocess\.', 'Subprocess usage'),
            (r'os\.system\s*\(', 'OS system call'),
            (r'pickle\.loads?\s*\(', 'Pickle deserialization'),
            (r'import\s+os\s+', 'OS import'),
            (r'import\s+subprocess\s+', 'Subprocess import'),
            (r'base64\.decode\s*\(', 'Base64 decoding'),
            (r'compile\s*\(.*code', 'Code compilation'),
            (r'__import__\s*\(', 'Dynamic import'),
        ]
        
        for pattern, description in suspicious_patterns:
            if re.search(pattern, content):
                risks.append(f"{description} found in: {filepath}")
                
    except (IOError, PermissionError, UnicodeDecodeError) as e:
        # 忽略二进制文件或无法读取的文件
        pass
        
    return risks

def scan_directory_for_risks(scan_path: str) -> Dict[str, List[str]]:
    """扫描目录查找潜在安全风险"""
    results = {
        'permission_risks': [],
        'content_risks': [],
        'hashes': {}
    }
    
    try:
        scan_dir = Path(scan_path)
        if not scan_dir.exists():
            print(f"Error: Path {scan_path} does not exist")
            return results
            
        if not scan_dir.is_dir():
            print(f"Error: {scan_path} is not a directory")
            return results
            
        for filepath in scan_dir.rglob('*'):
            if filepath.is_file():
                # 检查权限风险
                perm_risks = check_file_permissions(filepath)
                if perm_risks:
                    results['permission_risks'].extend(perm_risks)
                
                # 检查内容风险（只检查文本文件）
                try:
                    if filepath.suffix.lower() in ['.py', '.js', '.html', '.php', '.sh', '.bat', '.cmd', '.txt', '.json', '.yaml', '.yml', '.xml', '.cfg', '.conf']:
                        content_risks = check_suspicious_patterns(filepath)
                        if content_risks:
                            results['content_risks'].extend(content_risks)
                except Exception:
                    pass
                
                # 计算文件哈希
                file_hash = calculate_file_hash(filepath)
                results['hashes'][str(filepath)] = file_hash
                
    except Exception as e:
        print(f"Error scanning directory: {e}")
        
    return results

def generate_report(results: Dict) -> str:
    """生成安全扫描报告"""
    report = []
    report.append("=" * 60)
    report.append("       潜在安全风险扫描报告")
    report.append("=" * 60)
    report.append("")
    
    # 权限风险
    if results['permission_risks']:
        report.append("【权限安全风险】")
        for risk in results['permission_risks']:
            report.append(f"  - {risk}")
        report.append("")
    else:
        report.append("【权限安全风险】")
        report.append("  未发现明显的权限安全风险")
        report.append("")
    
    # 内容风险
    if results['content_risks']:
        report.append("【内容安全风险】")
        for risk in results['content_risks']:
            report.append(f"  - {risk}")
        report.append("")
    else:
        report.append("【内容安全风险】")
        report.append("  未发现明显的内容安全风险")
        report.append("")
    
    # 文件哈希
    if results['hashes']:
        report.append("【文件哈希值】")
        for filepath, hash_value in results['hashes'].items():
            report.append(f"  {filepath}: {hash_value}")
        report.append("")
    
    report.append("=" * 60)
    report.append("报告生成时间: " + __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    report.append("=" * 60)
    
    return "\n".join(report)

def main():
    """主函数"""
    print("开始扫描潜在安全风险...")
    print("提示: 默认扫描当前目录")
    print("-" * 40)
    
    # 可以指定扫描路径，默认当前目录
    scan_path = sys.argv[1] if len(sys.argv) > 1 else "."
    
    results = scan_directory_for_risks(scan_path)
    report = generate_report(results)
    
    print(report)
    
    # 将报告保存到文件
    try:
        with open('security_scan_report.txt', 'w', encoding='utf-8') as f:
            f.write(report)
        print("\n报告已保存到: security_scan_report.txt")
    except Exception as e:
        print(f"\n保存报告失败: {e}")

if __name__ == "__main__":
    main()