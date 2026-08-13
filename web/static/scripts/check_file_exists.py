import os
import sys

# 检查命令行参数
if len(sys.argv) < 2:
    print("错误：请提供文件路径作为参数")
    print("用法: python script.py <文件路径>")
    sys.exit(1)

file_path = sys.argv[1]

# 检查文件是否存在
if not os.path.exists(file_path):
    print(f"错误：文件 '{file_path}' 不存在")
    sys.exit(1)

# 检查是否为文件（而非目录）
if not os.path.isfile(file_path):
    print(f"错误：'{file_path}' 不是一个文件")
    sys.exit(1)

print(f"文件 '{file_path}' 存在")
print(f"文件大小: {os.path.getsize(file_path)} 字节")
print(f"最后修改时间: {os.path.getmtime(file_path)}")
print(f"绝对路径: {os.path.abspath(file_path)}")