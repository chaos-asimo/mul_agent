# 由于用户未实际上传文件，此处提供一个通用的文件分析脚本模板
# 该脚本可以分析CSV、JSON和TXT文件的基本统计信息

import os
import json
import csv
import argparse
from collections import Counter

def analyze_csv(file_path):
    """分析CSV文件的基本统计信息"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            rows = list(reader)
            
        print(f"文件类型: CSV")
        print(f"列数: {len(headers)}")
        print(f"行数: {len(rows)}")
        print(f"列名: {headers}")
        
        # 统计每列的非空值数量
        col_counts = [sum(1 for row in rows if row[i].strip()) for i in range(len(headers))]
        for header, count in zip(headers, col_counts):
            print(f"列 '{header}' 非空值数量: {count}")
            
    except Exception as e:
        print(f"分析CSV文件时出错: {e}")

def analyze_json(file_path):
    """分析JSON文件的基本结构"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"文件类型: JSON")
        
        if isinstance(data, dict):
            print(f"根对象键数量: {len(data.keys())}")
            print(f"根对象键: {list(data.keys())}")
        elif isinstance(data, list):
            print(f"列表长度: {len(data)}")
            if data:
                print(f"第一个元素类型: {type(data[0]).__name__}")
        else:
            print(f"数据类型: {type(data).__name__}")
            
    except Exception as e:
        print(f"分析JSON文件时出错: {e}")

def analyze_txt(file_path):
    """分析TXT文件的基本统计信息"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        words = content.split()
        
        print(f"文件类型: TXT")
        print(f"字符数: {len(content)}")
        print(f"行数: {len(lines)}")
        print(f"单词数: {len(words)}")
        
        # 词频统计（前10个最常见单词）
        word_counter = Counter(words)
        print("前10个最常见单词:")
        for word, count in word_counter.most_common(10):
            print(f"  '{word}': {count}")
            
    except Exception as e:
        print(f"分析TXT文件时出错: {e}")

def analyze_file(file_path):
    """根据文件类型自动分析文件"""
    if not os.path.exists(file_path):
        print(f"文件不存在: {file_path}")
        return
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.csv':
        analyze_csv(file_path)
    elif ext == '.json':
        analyze_json(file_path)
    elif ext in ('.txt', '.log'):
        analyze_txt(file_path)
    else:
        print(f"不支持的文件类型: {ext}")
        print(f"支持的文件类型: .csv, .json, .txt, .log")

if __name__ == "__main__":
    # 示例使用
    # 实际使用时，请替换为您的文件路径
    test_files = [
        "example.csv",
        "example.json",
        "example.txt"
    ]
    
    # 如果文件存在则分析，否则显示帮助信息
    for file_path in test_files:
        if os.path.exists(file_path):
            print(f"\n{'='*50}")
            print(f"分析文件: {file_path}")
            print('='*50)
            analyze_file(file_path)
    
    print("\n如需分析特定文件，请修改脚本中的test_files列表或使用命令行参数:")
    print("python script.py your_file.csv")