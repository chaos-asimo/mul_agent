import os
import sys
import re
import string
from collections import Counter

# 尝试导入必要的库，如果缺失则给出提示
try:
    import PyPDF2
except ImportError:
    print("错误: 缺少 'PyPDF2' 库。请运行: pip install PyPDF2")
    sys.exit(1)

try:
    import docx
except ImportError:
    print("错误: 缺少 'python-docx' 库。请运行: pip install python-docx")
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    print("错误: 缺少 'pandas' 库。请运行: pip install pandas")
    sys.exit(1)

try:
    import jieba
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False
    print("提示: 缺少 'jieba' 库。中文分词功能将使用简单的空格分割，建议安装以提升效果。运行: pip install jieba")


def read_txt_file(file_path):
    """读取 .txt 文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def read_pdf_file(file_path):
    """读取 .pdf 文件"""
    text = ""
    try:
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
    except Exception as e:
        raise Exception(f"PDF读取失败: {e}")
    return text

def read_docx_file(file_path):
    """读取 .docx 文件"""
    try:
        doc = docx.Document(file_path)
        return "\n".join([paragraph.text for paragraph in doc.paragraphs])
    except Exception as e:
        raise Exception(f"DOCX读取失败: {e}")

def read_csv_file(file_path):
    """读取 .csv 文件，将其转换为文本描述"""
    try:
        df = pd.read_csv(file_path)
        # 将DataFrame转换为简化的文本表示，包含列名和部分数据行
        text = "CSV文件内容摘要:\n"
        text += f"列名: {', '.join(df.columns)}\n"
        text += f"总行数: {len(df)}\n"
        # 如果数据太多，只取前5行作为示例
        sample_data = df.head(5).to_string(index=False)
        text += f"前5行数据:\n{sample_data}\n"
        return text
    except Exception as e:
        raise Exception(f"CSV读取失败: {e}")

def read_excel_file(file_path):
    """读取 .xlsx 文件"""
    try:
        df = pd.read_excel(file_path)
        text = "Excel文件内容摘要:\n"
        text += f"列名: {', '.join(df.columns)}\n"
        text += f"总行数: {len(df)}\n"
        sample_data = df.head(5).to_string(index=False)
        text += f"前5行数据:\n{sample_data}\n"
        return text
    except Exception as e:
        raise Exception(f"Excel读取失败: {e}")

def read_md_file(file_path):
    """读取 .md 文件，去除Markdown标记"""
    text = read_txt_file(file_path)
    # 简单去除Markdown标记
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'\*\*|\*|`', '', text)
    return text

def extract_text_from_file(file_path):
    """根据文件扩展名分发读取任务"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.txt':
        return read_txt_file(file_path)
    elif ext == '.pdf':
        return read_pdf_file(file_path)
    elif ext == '.docx':
        return read_docx_file(file_path)
    elif ext == '.csv':
        return read_csv_file(file_path)
    elif ext in ['.xlsx', '.xls']:
        return read_excel_file(file_path)
    elif ext == '.md':
        return read_md_file(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}。支持格式: .txt, .pdf, .docx, .csv, .xlsx, .md")

def simple_english_summarization(text, num_sentences=5):
    """
    基于句子频率的英文提取式摘要算法
    """
    if not text:
        return ""
    
    # 清理文本
    text = text.replace('\n', ' ')
    # 分割成句子 (简单按句号和换行分割)
    sentences = re.split(r'(?<=[.!?]) +', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return "无法提取文本。"

    # 分词并计算频率 (忽略停用词和标点)
    stop_words = set(["the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "by", "from", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "shall", "can", "need", "dare", "ought", "used", "it", "its", "this", "that", "these", "those", "i", "you", "he", "she", "we", "they", "what", "which", "who", "whom", "whose", "where", "when", "why", "how", "all", "each", "every", "both", "few", "many", "much", "some", "any", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "s", "t", "just", "don", "now", "of"])
    
    word_freq = Counter()
    for sentence in sentences:
        words = re.findall(r'\b[a-zA-Z]+\b', sentence.lower())
        for word in words:
            if word not in stop_words and len(word) > 2:
                word_freq[word] += 1
                
    # 如果没有有效词汇，返回前几个句子
    if not word_freq:
        return " ".join(sentences[:num_sentences])

    # 计算句子得分
    sentence_scores = {}
    for i, sentence in enumerate(sentences):
        score = 0
        words_in_sent = re.findall(r'\b[a-zA-Z]+\b', sentence.lower())
        for word in words_in_sent:
            if word in word_freq:
                score += word_freq[word]
        # 归一化并考虑句子位置（可选，这里简单处理）
        if sentence:
            sentence_scores[i] = score / len(words_in_sent) if words_in_sent else 0

    # 选择得分最高的句子
    sorted_sentences = sorted(sentence_scores.items(), key=lambda x: x[1], reverse=True)
    top_indices = sorted([idx for idx, _ in sorted_sentences[:num_sentences]])
    
    # 按原文顺序输出
    summary_sentences = [sentences[i] for i in sorted(top_indices)]
    return " ".join(summary_sentences)

def simple_chinese_summarization(text, num_sentences=5):
    """
    基于简单分词的中文提取式摘要算法
    """
    if not text:
        return ""

    # 简单按中文标点和换行分割句子
    sentences = re.split(r'(?<=[。！？\n])', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return "无法提取文本。"

    # 分词
    if HAS_JIEBA:
        words_list = [list(jieba.cut(s)) for s in sentences]
    else:
        # 简单按字符分割作为备选
        words_list = [list(s) for s in sentences]

    # 计算词频
    word_freq = Counter()
    for words in words_list:
        for word in words:
            if word not in string.punctuation and len(word) > 1:
                word_freq[word] += 1

    # 计算句子得分
    sentence_scores = {}
    for i, words in enumerate(words_list):
        score = 0
        for word in words:
            if word in word_freq:
                score += word_freq[word]
        if words:
            sentence_scores[i] = score / len(words)

    # 选择得分最高的句子
    sorted_sentences = sorted(sentence_scores.items(), key=lambda x: x[1], reverse=True)
    top_indices = sorted([idx for idx, _ in sorted_sentences[:num_sentences]])
    
    # 按原文顺序输出
    summary_sentences = [sentences[i] for i in sorted(top_indices)]
    return "\n".join(summary_sentences)

def detect_language_and_summarize(text):
    """
    简单检测语言并执行摘要
    """
    # 简单启发式检测：检查中文字符比例
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    total_chars = len(re.sub(r'\s+', '', text))
    
    if total_chars == 0:
        return ""
        
    ratio = chinese_chars / total_chars
    
    if ratio > 0.3: # 如果中文占比超过30%，认为是中文
        return simple_chinese_summarization(text)
    else:
        return simple_english_summarization(text)

def main():
    # 默认测试文件路径，用户可修改
    # 如果没有文件，创建一个示例文本文件进行测试
    test_file_path = "test_document.txt"
    
    if not os.path.exists(test_file_path):
        print(f"文件 '{test_file_path}' 不存在。正在创建一个示例文件用于演示...")
        sample_content = """
        Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected. It supports multiple programming paradigms, including structured, object-oriented and functional programming.

        It was conceived in the late 1980s by Guido van Rossum at Centrum Wiskunde & Informatica (CWI) in the Netherlands as a successor to the ABC programming language, which was inspired by SETL, capable of handling exception handling and interfacing with the Amoeba operating system.

        Key features of Python include:
        1. Easy to learn and read.
        2. Extensive standard library.
        3. Supports multiple programming paradigms.
        4. Dynamically typed.
        5. Interpreted language.

        Python is widely used in web development, data science, artificial intelligence, and automation.

        中文部分示例：
        Python是一门非常流行的编程语言。它以其简洁明了的语法而闻名。Python广泛应用于数据分析、人工智能、Web开发等领域。许多大型公司如Google、Netflix和Instagram都使用Python作为其主要开发语言之一。学习Python对于初学者来说是一个非常不错的选择，因为它易于上手且功能强大。
        """
        with open(test_file_path, 'w', encoding='utf-8') as f:
            f.write(sample_content)

    print(f"正在处理文件: {test_file_path}")
    
    try:
        # 1. 读取内容
        content = extract_text_from_file(test_file_path)
        
        # 2. 检查内容长度
        if len(content) < 10:
            print("内容过短，直接输出原始内容：")
            print("-" * 30)
            print(content)
            print("-" * 30)
        else:
            # 3. 生成摘要
            summary = detect_language_and_summarize(content)
            
            print("-" * 30)
            print("摘要结果：")
            print("-" * 30)
            print(summary)
            print("-" * 30)
            
            # 可选：保存摘要到文件
            summary_file = test_file_path.rsplit('.', 1)[0] + "_summary.txt"
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(summary)
            print(f"\n摘要已保存至: {summary_file}")

    except Exception as e:
        print(f"处理文件时发生错误: {e}")

if __name__ == "__main__":
    main()