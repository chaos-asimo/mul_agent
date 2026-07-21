import os

# 定义目标目录路径
directory_path = r"C:\develop\trae\mul_agent\uploads\images"

# 检查目录是否存在
if os.path.exists(directory_path):
    # 获取目录中的所有文件和子目录
    entries = os.listdir(directory_path)
    
    # 过滤出文件（排除子目录）
    file_count = sum(1 for entry in entries if os.path.isfile(os.path.join(directory_path, entry)))
    
    print(f"目录 '{directory_path}' 中的文件数量为: {file_count}")
else:
    print(f"目录 '{directory_path}' 不存在。")