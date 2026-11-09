# 由于无法直接访问用户附件，本脚本模拟了一个通用的文件评价器
# 它可以读取本地文件并基于文件大小、行数、编码等基本信息进行评价
# 用户需将文件路径替换为实际附件路径

import os
import sys

def evaluate_file(file_path: str) -> dict:
    """
    对指定文件进行基本评价
    
    Args:
        file_path (str): 文件路径
        
    Returns:
        dict: 包含文件评价结果的字典
    """
    if not os.path.exists(file_path):
        return {"error": f"文件不存在: {file_path}"}
    
    if not os.path.isfile(file_path):
        return {"error": f"路径不是文件: {file_path}"}
    
    try:
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        
        # 尝试读取文件内容以获取行数
        line_count = 0
        has_content = False
        file_type = "unknown"
        
        # 确定文件类型
        _, extension = os.path.splitext(file_path)
        extension = extension.lower()
        
        if extension in ['.py', '.js', '.java', '.c', '.cpp', '.h', '.txt', '.md', '.csv', '.json', '.xml', '.html', '.css']:
            file_type = "text"
        elif extension in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg']:
            file_type = "image"
        elif extension in ['.pdf', '.doc', '.docx', '.xls', '.xlsx']:
            file_type = "document"
        elif extension in ['.zip', '.tar', '.gz', '.rar']:
            file_type = "archive"
        elif extension in ['.mp3', '.wav', '.mp4', '.avi']:
            file_type = "media"
        
        # 尝试读取文本文件
        if file_type == "text":
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    line_count = len(lines)
                    has_content = line_count > 0
            except UnicodeDecodeError:
                # 如果UTF-8解码失败，尝试其他编码
                try:
                    with open(file_path, 'r', encoding='latin-1') as f:
                        lines = f.readlines()
                        line_count = len(lines)
                        has_content = line_count > 0
                except Exception:
                    file_type = "binary"
                    line_count = 0
                    has_content = file_size > 0
            except Exception:
                file_type = "binary"
                line_count = 0
                has_content = file_size > 0
        else:
            file_type = "binary"
            has_content = file_size > 0
        
        # 生成评价
        size_category = ""
        if file_size < 1024:
            size_category = "小文件 (< 1KB)"
        elif file_size < 1024 * 1024:
            size_category = "中等文件 (< 1MB)"
        elif file_size < 1024 * 1024 * 10:
            size_category = "较大文件 (< 10MB)"
        else:
            size_category = "大文件 (>= 10MB)"
        
        quality_score = 0
        comments = []
        
        # 基于文件类型和内容进行评价
        if file_type == "text":
            if has_content:
                quality_score += 50
                comments.append("文件包含内容")
                if line_count > 0:
                    quality_score += min(30, line_count // 10)
                    comments.append(f"文件有 {line_count} 行")
                if file_size > 0:
                    quality_score += 20
                    comments.append("文件大小合理")
            else:
                quality_score += 10
                comments.append("文件为空")
        elif file_type == "image":
            if file_size > 100:  # 图片通常不会太小
                quality_score += 50
                comments.append("图片文件存在")
            if file_size > 1024 * 1024:  # 大于1MB的图片
                quality_score += 30
                comments.append("图片分辨率可能较高")
            if file_size < 100:
                quality_score += 10
                comments.append("图片文件非常小，可能损坏")
        elif file_type == "document":
            if file_size > 1000:
                quality_score += 50
                comments.append("文档包含内容")
            else:
                quality_score += 20
                comments.append("文档可能为空或内容很少")
        elif file_type == "archive":
            if file_size > 100:
                quality_score += 50
                comments.append("压缩包存在")
            else:
                quality_score += 10
                comments.append("压缩包可能为空")
        elif file_type == "media":
            if file_size > 10000:
                quality_score += 50
                comments.append("媒体文件存在")
            else:
                quality_score += 10
                comments.append("媒体文件可能损坏")
        else:
            if has_content:
                quality_score += 30
                comments.append("二进制文件存在")
            else:
                quality_score += 5
                comments.append("文件为空")
        
        # 根据文件大小调整评分
        if file_size == 0:
            quality_score = 0
            comments = ["文件为空"]
        
        # 限制评分在0-100之间
        quality_score = max(0, min(100, quality_score))
        
        result = {
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "file_size": file_size,
            "file_size_category": size_category,
            "file_type": file_type,
            "line_count": line_count if file_type == "text" else "N/A",
            "has_content": has_content,
            "quality_score": quality_score,
            "comments": comments
        }
        
        return result
        
    except Exception as e:
        return {"error": f"评价文件时出错: {str(e)}"}


def print_evaluation(result: dict) -> None:
    """
    打印文件评价结果
    
    Args:
        result (dict): 文件评价结果
    """
    if "error" in result:
        print(f"错误: {result['error']}")
        return
    
    print("=" * 50)
    print("文件评价报告")
    print("=" * 50)
    print(f"文件名称: {result['file_name']}")
    print(f"文件路径: {result['file_path']}")
    print(f"文件大小: {result['file_size']} 字节 ({result['file_size_category']})")
    print(f"文件类型: {result['file_type']}")
    
    if isinstance(result['line_count'], int):
        print(f"行数: {result['line_count']}")
    else:
        print(f"行数: {result['line_count']}")
    
    print(f"包含内容: {'是' if result['has_content'] else '否'}")
    print(f"质量评分: {result['quality_score']}/100")
    print("评价详情:")
    for comment in result['comments']:
        print(f"  - {comment}")
    print("=" * 50)


if __name__ == "__main__":
    # 默认测试文件路径，用户应替换为实际附件路径
    test_file_path = "attachment.txt"
    
    # 如果命令行提供了文件路径，使用命令行参数
    if len(sys.argv) > 1:
        test_file_path = sys.argv[1]
    
    print(f"正在评价文件: {test_file_path}")
    result = evaluate_file(test_file_path)
    print_evaluation(result)