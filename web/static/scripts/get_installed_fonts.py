import subprocess
import platform

def get_installed_fonts():
    """
    获取系统中安装的字体列表。
    支持 Windows, macOS 和 Linux。
    """
    system = platform.system()
    fonts = []
    
    try:
        if system == "Windows":
            # 在 Windows 上，字体通常安装在 C:\Windows\Fonts\
            import os
            font_dir = r"C:\Windows\Fonts"
            if os.path.exists(font_dir):
                for filename in os.listdir(font_dir):
                    # 只保留字体文件扩展名
                    if filename.lower().endswith(('.ttf', '.otf', '.ttc', '.fon')):
                        fonts.append(filename)
        
        elif system == "Darwin":  # macOS
            # macOS 字体主要位于 /Library/Fonts 和 ~/Library/Fonts
            font_dirs = [
                "/Library/Fonts",
                os.path.expanduser("~/Library/Fonts")
            ]
            for font_dir in font_dirs:
                if os.path.exists(font_dir):
                    for filename in os.listdir(font_dir):
                        if filename.lower().endswith(('.ttf', '.otf', '.ttc', '.dfont')):
                            fonts.append(filename)
        
        elif system == "Linux":
            # Linux 字体通常位于 /usr/share/fonts 和 ~/.local/share/fonts
            font_dirs = [
                "/usr/share/fonts",
                os.path.expanduser("~/.local/share/fonts")
            ]
            for font_dir in font_dirs:
                if os.path.exists(font_dir):
                    # 递归查找所有字体文件
                    for root, dirs, files in os.walk(font_dir):
                        for filename in files:
                            if filename.lower().endswith(('.ttf', '.otf', '.ttc', '.pfa', '.pfb')):
                                fonts.append(filename)
        else:
            print(f"不支持的操作系统: {system}")
            return []
    
    except PermissionError:
        print("权限不足，无法访问某些字体目录。")
    except Exception as e:
        print(f"发生错误: {e}")
    
    return fonts

if __name__ == "__main__":
    print("正在获取已安装的字体...")
    fonts = get_installed_fonts()
    
    if fonts:
        print(f"共找到 {len(fonts)} 个字体文件:")
        for i, font in enumerate(sorted(fonts), 1):
            print(f"{i}. {font}")
    else:
        print("未找到字体文件。")