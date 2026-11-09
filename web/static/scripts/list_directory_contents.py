import os

def list_files_in_directory(directory_path: str):
    """
    列出指定目录下的所有文件和子目录
    """
    # 检查目录是否存在
    if not os.path.exists(directory_path):
        print(f"错误: 目录 '{directory_path}' 不存在。")
        return
    
    # 检查是否是目录
    if not os.path.isdir(directory_path):
        print(f"错误: '{directory_path}' 不是一个目录。")
        return
    
    try:
        # 列出目录内容
        entries = os.listdir(directory_path)
        
        if not entries:
            print(f"目录 '{directory_path}' 是空的。")
            return
        
        # 分类显示文件和目录
        files = []
        dirs = []
        
        for entry in entries:
            full_path = os.path.join(directory_path, entry)
            if os.path.isdir(full_path):
                dirs.append(entry)
            else:
                files.append(entry)
        
        # 打印结果
        print(f"目录: {directory_path}")
        print(f"子目录 ({len(dirs)}):")
        for d in sorted(dirs):
            print(f"  📁 {d}")
        
        print(f"\n文件 ({len(files)}):")
        for f in sorted(files):
            file_path = os.path.join(directory_path, f)
            file_size = os.path.getsize(file_path)
            print(f"  📄 {f} ({file_size} bytes)")
            
    except PermissionError:
        print(f"错误: 没有权限访问目录 '{directory_path}'。")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    target_directory = r"C:\develop\trae\mul_agent\uploads"
    list_files_in_directory(target_directory)