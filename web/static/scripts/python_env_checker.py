import platform
import sys
import os
import subprocess
import json

def check_python_version():
    print("Python版本:", platform.python_version())
    print("Python编译器:", platform.python_compiler())
    print("Python实现:", platform.python_implementation())
    print("-" * 30)

def check_system_info():
    print("操作系统:", platform.system())
    print("操作系统版本:", platform.version())
    print("处理器:", platform.processor())
    print("机器类型:", platform.machine())
    print("节点名:", platform.node())
    print("-" * 30)

def check_environment_variables():
    print("当前工作目录:", os.getcwd())
    print("Python路径:", sys.executable)
    print("Python路径列表:")
    for p in sys.path:
        print(f"  - {p}")
    print("-" * 30)

def check_installed_packages():
    try:
        import pip
        print("已安装的pip包 (前20个):")
        packages = pip.get_installed_distributions()
        for i, pkg in enumerate(packages):
            if i >= 20:
                break
            print(f"  - {pkg.project_name}=={pkg.version}")
        print(f"  ... 共 {len(list(packages))} 个包")
    except ImportError:
        print("pip未检测到，尝试使用sysconfig...")
        try:
            import sysconfig
            print("系统配置路径:", sysconfig.get_paths())
        except Exception as e:
            print(f"检查包列表失败: {e}")
    print("-" * 30)

def check_disk_space():
    try:
        usage = os.statvfs(os.getcwd())
        free_bytes = usage.f_bavail * usage.f_frsize
        total_bytes = usage.f_blocks * usage.f_frsize
        free_gb = free_bytes / (1024**3)
        total_gb = total_bytes / (1024**3)
        print(f"磁盘空间:")
        print(f"  总容量: {total_gb:.2f} GB")
        print(f"  可用空间: {free_gb:.2f} GB")
    except Exception as e:
        print(f"检查磁盘空间失败: {e}")
    print("-" * 30)

def check_network():
    import socket
    try:
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        print(f"主机名: {hostname}")
        print(f"IP地址: {ip_address}")
    except Exception as e:
        print(f"检查网络信息失败: {e}")
    print("-" * 30)

def check_python_modules():
    common_modules = ['os', 'sys', 'json', 'math', 'datetime', 'collections', 'itertools', 'functools', 're', 'io', 'pathlib', 'subprocess', 'threading', 'multiprocessing', 'logging', 'argparse', 'unittest', 'pytest']
    print("常用标准库模块检查:")
    missing = []
    for mod in common_modules:
        try:
            __import__(mod)
            print(f"  [OK] {mod}")
        except ImportError:
            print(f"  [FAIL] {mod}")
            missing.append(mod)
    if missing:
        print(f"缺失模块: {', '.join(missing)}")
    else:
        print("所有常用标准库模块正常。")
    print("-" * 30)

def main():
    print("=" * 50)
    print("       Python 环境自检报告")
    print("=" * 50)
    
    check_python_version()
    check_system_info()
    check_environment_variables()
    check_network()
    check_disk_space()
    check_installed_packages()
    check_python_modules()
    
    print("=" * 50)
    print("       环境自检完成")
    print("=" * 50)

if __name__ == "__main__":
    main()