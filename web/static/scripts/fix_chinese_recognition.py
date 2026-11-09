import subprocess
import sys

def fix_chinese_recognition_issue():
    """
    修复OCR或文档处理中中文无法识别的问题。
    常见原因：
    1. 字体缺失或嵌入不正确
    2. 编码问题（如UTF-8 vs GBK）
    3. OCR引擎未正确配置支持中文
    
    本脚本演示如何：
    - 检查并设置正确的文件编码
    - 使用PyMuPDF (fitz) 提取文本并验证中文可读性
    - 提供解决方案建议
    """
    
    # 检查必要的库是否安装
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("请先安装 PyMuPDF: pip install PyMuPDF")
        return

    def check_pdf_chinese(content: str) -> bool:
        """检查文本中是否包含可识别的中文字符"""
        if not content:
            return False
        # 中文字符的Unicode范围
        chinese_pattern = '[\u4e00-\u9fff]'
        for char in content:
            if '\u4e00' <= char <= '\u9fff':
                return True
        return False

    def read_file_with_encoding(filepath: str, encodings: list = None):
        """
        尝试用多种编码读取文件
        
        Args:
            filepath: 文件路径
            encodings: 尝试的编码列表
            
        Returns:
            tuple: (成功读取的内容, 使用的编码) 或 (None, None) if failed
        """
        if encodings is None:
            encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'big5']
            
        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    content = f.read()
                    if content:
                        return content, encoding
            except (UnicodeDecodeError, UnicodeError):
                continue
        return None, None

    def extract_text_from_pdf(pdf_path: str) -> str:
        """
        从PDF中提取文本
        
        Args:
            pdf_path: PDF文件路径
            
        Returns:
            提取的文本内容
        """
        try:
            doc = fitz.open(pdf_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        except Exception as e:
            print(f"提取PDF文本时出错: {e}")
            return ""

    def generate_solution_report(pdf_path: str, text_content: str):
        """生成解决方案报告"""
        print("=" * 60)
        print("中文无法识别问题诊断报告")
        print("=" * 60)
        
        # 1. 检查文本内容
        has_chinese = check_chinese_in_text(text_content)
        print(f"\n1. 文本中包含中文: {'是' if has_chinese else '否'}")
        
        if has_chinese:
            # 检查中文是否可读
            sample_chinese = extract_chinese_chars(text_content)
            print(f"   样本中文字符: {sample_chinese[:50]}")
            
            # 检查是否有乱码
            if is_mojibake(text_content):
                print("   ⚠️  检测到可能的编码错误（乱码）")
                print("   建议: 使用正确的编码重新读取文件")
            else:
                print("   ✓ 中文可读性正常")
        else:
            print("   未检测到中文字符")
            print("   建议: 检查源文件是否包含中文")
        
        # 2. 提供解决方案
        print("\n2. 解决方案建议:")
        print("   a) 如果是PDF文件:")
        print("      - 确保PDF嵌入中文字体")
        print("      - 使用 PyMuPDF 提取文本（支持中文）")
        print("   b) 如果是文本文件:")
        print("      - 尝试不同编码读取（UTF-8, GBK等）")
        print("   c) 如果是OCR场景:")
        print("      - 使用支持中文的OCR引擎（如PaddleOCR、Tesseract with chi_sim）")
        print("      - 预处理图像提高识别率")
        
        print("\n" + "=" * 60)

    def check_chinese_in_text(text: str) -> bool:
        """检查文本中是否包含中文字符"""
        if not text:
            return False
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                return True
        return False

    def extract_chinese_chars(text: str, count: int = 10) -> str:
        """提取文本中的中文字符"""
        chinese_chars = []
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                chinese_chars.append(char)
                if len(chinese_chars) >= count:
                    break
        return ''.join(chinese_chars)

    def is_mojibake(text: str) -> bool:
        """
        检测文本是否可能是乱码
        
        简单的启发式方法：检查是否有异常的字节序列或不可打印字符
        """
        if not text:
            return False
        
        # 检查是否有常见的乱码模式
        mojibake_patterns = [
            'ï¿½',  # UTF-8 BOM or replacement character
            'â€"',  # Common UTF-8 misinterpretation as Latin-1
            'ä¸­',  # "中" when UTF-8 is read as Latin-1
            'æ–‡',  # "文" when UTF-8 is read as Latin-1
        ]
        
        for pattern in mojibake_patterns:
            if pattern in text:
                return True
        
        # 检查是否有大量不可打印字符
        non_printable_count = sum(1 for char in text if not char.isprintable() and not char.isspace())
        if len(text) > 0 and non_printable_count / len(text) > 0.1:
            return True
        
        return False

    # 主程序
    print("中文无法识别问题诊断工具")
    print("请提供PDF或文本文件路径以进行诊断")
    
    # 示例：使用测试文件
    test_pdf_path = "sample.pdf"
    test_text_path = "sample.txt"
    
    # 创建测试文件用于演示
    print("\n创建测试文件...")
    
    # 创建测试文本文件（UTF-8编码，包含中文）
    with open(test_text_path, 'w', encoding='utf-8') as f:
        f.write("这是一个测试文本，包含中文字符。\n")
        f.write("Hello World! 你好世界！\n")
        f.write("中文识别测试：\n")
        f.write("一、二、三、四、五\n")
    
    print(f"创建文本文件: {test_text_path}")
    
    # 读取文本文件
    print(f"\n读取文件: {test_text_path}")
    content, encoding = read_file_with_encoding(test_text_path)
    
    if content:
        print(f"成功使用编码: {encoding}")
        print(f"文件内容:\n{content}")
        
        # 诊断
        generate_solution_report(test_text_path, content)
        
        # 验证中文可读性
        if check_chinese_in_text(content):
            chinese_sample = extract_chinese_chars(content)
            print(f"\n✓ 成功提取中文字符: {chinese_sample}")
            print("✓ 中文识别正常")
        else:
            print("\n✗ 未检测到中文字符")
            print("✗ 中文识别失败")
    else:
        print("无法读取文件，请检查文件路径")
    
    # 清理测试文件
    import os
    if os.path.exists(test_text_path):
        os.remove(test_text_path)
        print(f"\n已清理测试文件: {test_text_path}")

if __name__ == "__main__":
    fix_chinese_recognition_issue()