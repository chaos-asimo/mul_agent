import os
import glob
import argparse

def find_files(directory, filename_pattern="*", recursive=True):
    """
    在指定目录中查找符合文件名模式的文件
    
    参数:
    directory: 要搜索的目录路径
    filename_pattern: 文件名匹配模式，默认"*"表示所有文件
    recursive: 是否递归搜索子目录，默认为True
    
    返回:
    找到的文件路径列表
    """
    found_files = []
    
    if not os.path.exists(directory):
        print(f"错误: 目录 '{directory}' 不存在")
        return found_files
    
    if not os.path.isdir(directory):
        print(f"错误: '{directory}' 不是一个目录")
        return found_files
    
    if recursive:
        # 递归搜索所有子目录
        search_pattern = os.path.join(directory, "**", filename_pattern)
        found_files.extend(glob.glob(search_pattern, recursive=True))
    else:
        # 只搜索当前目录
        search_pattern = os.path.join(directory, filename_pattern)
        found_files.extend(glob.glob(search_pattern))
    
    return found_files

def main():
    parser = argparse.ArgumentParser(description="在指定目录中查找文件")
    parser.add_argument("directory", help="要搜索的目录路径")
    parser.add_argument("-p", "--pattern", default="*", help="文件名匹配模式，默认为'*'表示所有文件")
    parser.add_argument("-nr", "--no-recursive", action="store_true", help="不递归搜索子目录")
    
    args = parser.parse_args()
    
    recursive = not args.no_recursive
    
    print(f"正在目录 '{args.directory}' 中查找匹配模式 '{args.pattern}' 的文件...")
    print(f"递归搜索: {'是' if recursive else '否'}")
    print("-" * 50)
    
    found_files = find_files(args.directory, args.pattern, recursive)
    
    if found_files:
        print(f"找到 {len(found_files)} 个文件:")
        for file_path in found_files:
            print(f"  {file_path}")
    else:
        print("未找到匹配的文件")

if __name__ == "__main__":
    main()