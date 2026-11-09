import sys
import os
import platform
import subprocess

def check_environment():
    print("=" * 50)
    print("运行环境检查报告")
    print("=" * 50)
    
    # Python 版本
    print(f"\nPython 版本: {sys.version}")
    print(f"Python 路径: {sys.executable}")
    
    # 操作系统信息
    print(f"\n操作系统: {platform.system()}")
    print(f"操作系统版本: {platform.version()}")
    print(f"架构: {platform.machine()}")
    print(f"处理器: {platform.processor()}")
    
    # 当前工作目录
    print(f"\n当前工作目录: {os.getcwd()}")
    
    # 环境变量
    print(f"\n系统路径:")
    for path in sys.path:
        print(f"  - {path}")
    
    # 检查关键模块
    print(f"\n关键模块检查:")
    modules_to_check = ['fpdf', 'numpy', 'pandas', 'requests', 'json', 'os', 'sys']
    for module_name in modules_to_check:
        try:
            __import__(module_name)
            print(f"  ✓ {module_name}: 已安装")
        except ImportError:
            print(f"  ✗ {module_name}: 未安装")
    
    # 磁盘空间
    try:
        disk_usage = os.statvfs(os.getcwd())
        free_space = disk_usage.f_frsize * disk_usage.f_bavail
        free_space_gb = free_space / (1024 ** 3)
        print(f"\n可用磁盘空间: {free_space_gb:.2f} GB")
    except Exception as e:
        print(f"\n无法获取磁盘空间信息: {e}")
    
    # 打印当前时间
    from datetime import datetime
    print(f"\n检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("\n" + "=" * 50)
    print("环境检查完成")
    print("=" * 50)

if __name__ == "__main__":
    check_environment()