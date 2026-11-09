import os
import sys
import json
import hashlib

def calculate_file_hash(filepath: str, algorithm: str = 'sha256') -> str:
    """
    计算文件的哈希值，用于验证文件完整性。
    
    Args:
        filepath: 文件路径
        algorithm: 哈希算法名称 (默认 sha256)
    
    Returns:
        哈希值字符串
    """
    try:
        hash_func = hashlib.new(algorithm)
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    except Exception as e:
        return f"Error: {str(e)}"

def get_file_metadata(filepath: str) -> dict:
    """
    获取文件的基本元数据。
    
    Args:
        filepath: 文件路径
    
    Returns:
        包含文件元数据的字典
    """
    try:
        stat_info = os.stat(filepath)
        return {
            "filename": os.path.basename(filepath),
            "path": os.path.abspath(filepath),
            "size_bytes": stat_info.st_size,
            "size_human": f"{stat_info.st_size / (1024 ** 2):.2f} MB" if stat_info.st_size > 1024**2 else f"{stat_info.st_size / 1024:.2f} KB",
            "created_time": stat_info.st_ctime,
            "modified_time": stat_info.st_mtime,
            "is_file": os.path.isfile(filepath),
            "is_directory": os.path.isdir(filepath)
        }
    except Exception as e:
        return {"error": str(e)}

def analyze_text_content(filepath: str) -> dict:
    """
    分析文本文件的内容特征。
    
    Args:
        filepath: 文件路径
    
    Returns:
        包含文本分析结果的字典
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        lines = content.split('\n')
        words = content.split()
        
        # 统计字符频率
        char_freq = {}
        for char in content:
            char_freq[char] = char_freq.get(char, 0) + 1
        
        # 统计单词频率
        word_freq = {}
        for word in words:
            word_freq[word.lower()] = word_freq.get(word.lower(), 0) + 1
        
        # 获取最常见的单词
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            "total_characters": len(content),
            "total_lines": len(lines),
            "total_words": len(words),
            "unique_words": len(set(words)),
            "avg_word_length": sum(len(word) for word in words) / len(words) if words else 0,
            "top_10_words": sorted_words,
            "encoding_detected": "utf-8"
        }
    except Exception as e:
        return {"error": f"Text analysis failed: {str(e)}"}

def analyze_binary_content(filepath: str) -> dict:
    """
    分析二进制文件的内容特征。
    
    Args:
        filepath: 文件路径
    
    Returns:
        包含二进制文件分析结果的字典
    """
    try:
        with open(filepath, 'rb') as f:
            # 读取前1024字节进行分析
            header = f.read(1024)
        
        # 统计字节频率
        byte_freq = {}
        for byte in header:
            byte_freq[byte] = byte_freq.get(byte, 0) + 1
        
        # 计算熵（近似值）
        total_bytes = len(header)
        entropy = 0
        if total_bytes > 0:
            for count in byte_freq.values():
                if count > 0:
                    probability = count / total_bytes
                    entropy -= probability * (probability).bit_length()  # 简化熵计算
        
        return {
            "file_type_hint": "binary",
            "header_bytes": header[:50].hex(),  # 显示前50字节的十六进制表示
            "unique_bytes_in_header": len(byte_freq),
            "most_common_bytes": sorted(byte_freq.items(), key=lambda x: x[1], reverse=True)[:5],
            "entropy_approximation": entropy
        }
    except Exception as e:
        return {"error": f"Binary analysis failed: {str(e)}"}

def evaluate_file(filepath: str) -> dict:
    """
    全面评估文件内容。
    
    Args:
        filepath: 文件路径
    
    Returns:
        包含文件评估结果的字典
    """
    if not os.path.exists(filepath):
        return {"error": f"File not found: {filepath}"}
    
    if not os.path.isfile(filepath):
        return {"error": f"Not a file: {filepath}"}
    
    # 获取基本元数据
    metadata = get_file_metadata(filepath)
    
    # 计算哈希值
    file_hash = calculate_file_hash(filepath)
    
    # 根据文件大小和扩展名决定分析方法
    file_extension = os.path.splitext(filepath)[1].lower()
    file_size = os.path.getsize(filepath)
    
    analysis_result = {}
    
    # 对于小文件进行内容分析
    if file_size <= 10 * 1024 * 1024:  # 小于10MB
        if file_extension in ['.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.csv', '.md']:
            analysis_result = analyze_text_content(filepath)
        elif file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.pdf', '.exe', '.dll']:
            analysis_result = analyze_binary_content(filepath)
        else:
            # 尝试作为文本分析，如果失败则作为二进制分析
            try:
                analysis_result = analyze_text_content(filepath)
            except:
                analysis_result = analyze_binary_content(filepath)
    else:
        analysis_result = {
            "note": "File too large for detailed content analysis",
            "suggestion": "Consider analyzing specific sections of the file"
        }
    
    # 综合评估
    evaluation = {
        "metadata": metadata,
        "hash": file_hash,
        "analysis": analysis_result,
        "overall_assessment": {
            "file_accessible": True,
            "file_size_category": "small" if file_size < 1024**2 else "medium" if file_size < 1024**3 else "large",
            "content_type": "text" if file_extension in ['.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.csv', '.md'] else "binary" if file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.pdf', '.exe', '.dll'] else "unknown",
            "recommendations": []
        }
    }
    
    # 添加建议
    if file_size > 100 * 1024 * 1024:  # 大于100MB
        evaluation["overall_assessment"]["recommendations"].append("Consider compressing large files")
    
    if file_extension in ['.exe', '.dll', '.bat', '.cmd']:
        evaluation["overall_assessment"]["recommendations"].append("Review executable files for security")
    
    if file_extension in ['.txt', '.py', '.js']:
        evaluation["overall_assessment"]["recommendations"].append("Text files can be reviewed for content quality")
    
    return evaluation

def main():
    """
    主函数：评估指定文件的内容。
    """
    if len(sys.argv) < 2:
        print("Usage: python script.py <filepath>")
        print("Example: python script.py document.txt")
        sys.exit(1)
    
    filepath = sys.argv[1]
    
    print(f"Evaluating file: {filepath}")
    print("=" * 50)
    
    try:
        result = evaluate_file(filepath)
        
        if "error" in result:
            print(f"Error: {result['error']}")
            return
        
        # 输出评估结果
        print("\nFile Metadata:")
        for key, value in result["metadata"].items():
            if key not in ['created_time', 'modified_time']:  # 跳过时间戳的原始值
                print(f"  {key}: {value}")
        
        print(f"\nFile Hash (SHA256): {result['hash']}")
        
        print("\nContent Analysis:")
        if isinstance(result["analysis"], dict):
            for key, value in result["analysis"].items():
                if key == "top_10_words" and isinstance(value, list):
                    print(f"  {key}:")
                    for word, count in value:
                        print(f"    '{word}': {count}")
                elif key == "most_common_bytes" and isinstance(value, list):
                    print(f"  {key}:")
                    for byte_val, count in value:
                        print(f"    Byte {byte_val}: {count}")
                else:
                    print(f"  {key}: {value}")
        else:
            print(f"  {result['analysis']}")
        
        print("\nOverall Assessment:")
        for key, value in result["overall_assessment"].items():
            if key == "recommendations" and isinstance(value, list):
                print(f"  {key}:")
                for rec in value:
                    print(f"    - {rec}")
            else:
                print(f"  {key}: {value}")
        
        print("\n" + "=" * 50)
        print("Evaluation completed successfully.")
        
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()