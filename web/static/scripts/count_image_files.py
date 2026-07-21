import os
from pathlib import Path

def count_image_files(directory='uploads'):
    """
    统计指定目录下有多少图片文件
    
    支持的图片格式: jpg, jpeg, png, gif, bmp, tiff, webp, svg
    """
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.svg'}
    
    # 检查目录是否存在
    dir_path = Path(directory)
    if not dir_path.exists():
        print(f"目录 '{directory}' 不存在")
        return 0
    if not dir_path.is_dir():
        print(f"'{directory}' 不是一个目录")
        return 0
    
    image_count = 0
    image_files = []
    
    # 遍历目录中的所有文件
    for item in dir_path.iterdir():
        if item.is_file() and item.suffix.lower() in image_extensions:
            image_count += 1
            image_files.append(item.name)
    
    # 输出结果
    print(f"在 '{directory}' 目录下找到 {image_count} 个图片文件:")
    if image_files:
        for idx, filename in enumerate(sorted(image_files), 1):
            print(f"  {idx}. {filename}")
    else:
        print("  未找到任何图片文件")
    
    return image_count

if __name__ == '__main__':
    count_image_files()