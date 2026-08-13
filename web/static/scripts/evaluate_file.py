# 注意：此脚本假设“评价附件”是指对文件内容进行基本的质量或完整性评估。
# 由于没有具体的附件文件，这里模拟一个常见的文件评价场景：
# 1. 检查文件是否存在
# 2. 检查文件大小
# 3. 检查文件扩展名是否符合预期
# 4. 读取文件内容并计算基本统计信息（如行数、字符数）

import os
import sys

def evaluate_file(file_path):
    """
    对指定文件进行基本评价
    
    参数:
    file_path (str): 文件路径
    
    返回:
    dict: 包含评价结果的字典
    """
    result = {
        'exists': False,
        'size': 0,
        'extension': '',
        'valid_extension': False,
        'line_count': 0,
        'char_count': 0,
        'error': None
    }
    
    # 定义期望的扩展名列表（可根据需求修改）
    expected_extensions = ['.txt', '.csv', '.json', '.py', '.md']
    
    try:
        # 检查文件是否存在
        if not os.path.exists(file_path):
            result['error'] = f"文件不存在: {file_path}"
            return result
        
        result['exists'] = True
        
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        result['size'] = file_size
        
        # 获取文件扩展名
        _, ext = os.path.splitext(file_path)
        result['extension'] = ext.lower()
        
        # 检查扩展名是否有效
        result['valid_extension'] = ext.lower() in expected_extensions
        
        # 尝试读取文件内容并进行统计
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                result['char_count'] = len(content)
                result['line_count'] = content.count('\n') + (1 if content and not content.endswith('\n') else 0)
        except UnicodeDecodeError:
            result['error'] = "文件编码错误，无法以UTF-8读取"
        except Exception as e:
            result['error'] = f"读取文件时出错: {str(e)}"
            
    except Exception as e:
        result['error'] = f"评价文件时出错: {str(e)}"
    
    return result

def main():
    """
    主函数，演示如何评价文件
    """
    # 示例：评价当前目录下的一个示例文件
    # 如果当前目录下没有test.txt，则创建一个用于演示
    test_file = 'test.txt'
    
    if not os.path.exists(test_file):
        # 创建示例文件
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("这是一个测试文件。\n")
            f.write("用于演示文件评价功能。\n")
            f.write("第二行内容。\n")
        print(f"创建了示例文件: {test_file}")
    
    # 评价文件
    evaluation = evaluate_file(test_file)
    
    # 输出评价结果
    print("=" * 50)
    print("文件评价报告")
    print("=" * 50)
    
    if evaluation['error']:
        print(f"错误: {evaluation['error']}")
    else:
        print(f"文件是否存在: {evaluation['exists']}")
        print(f"文件大小: {evaluation['size']} 字节")
        print(f"文件扩展名: {evaluation['extension']}")
        print(f"扩展名是否有效: {evaluation['valid_extension']}")
        print(f"行数: {evaluation['line_count']}")
        print(f"字符数: {evaluation['char_count']}")
    
    print("=" * 50)

if __name__ == "__main__":
    main()