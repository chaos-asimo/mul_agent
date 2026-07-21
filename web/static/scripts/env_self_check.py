import os
import sys
import platform
import subprocess
import shutil
import socket
import psutil
import datetime

def check_python_version():
    """检查Python版本"""
    print(f"Python版本: {sys.version}")
    print(f"Python路径: {sys.executable}")
    required_version = (3, 8, 0)
    current_version = sys.version_info[:3]
    if current_version >= required_version:
        print("✓ Python版本满足要求 (>= 3.8.0)")
        return True
    else:
        print("✗ Python版本过低，需要 >= 3.8.0")
        return False

def check_system_info():
    """检查系统信息"""
    print(f"\n操作系统: {platform.system()} {platform.release()}")
    print(f"系统架构: {platform.machine()}")
    print(f"处理器: {platform.processor()}")
    print(f"节点名称: {platform.node()}")
    return True

def check_disk_space():
    """检查磁盘空间"""
    print("\n磁盘空间检查:")
    try:
        usage = psutil.disk_usage('/')
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        free_gb = usage.free / (1024 ** 3)
        print(f"总空间: {total_gb:.2f} GB")
        print(f"已用: {used_gb:.2f} GB")
        print(f"可用: {free_gb:.2f} GB")
        if free_gb > 1:
            print("✓ 磁盘空间充足")
            return True
        else:
            print("✗ 磁盘空间不足")
            return False
    except Exception as e:
        print(f"✗ 无法检查磁盘空间: {e}")
        return False

def check_memory():
    """检查内存"""
    print("\n内存检查:")
    try:
        vm = psutil.virtual_memory()
        total_gb = vm.total / (1024 ** 3)
        available_gb = vm.available / (1024 ** 3)
        percent = vm.percent
        print(f"总内存: {total_gb:.2f} GB")
        print(f"可用内存: {available_gb:.2f} GB")
        print(f"内存使用率: {percent}%")
        if percent < 90:
            print("✓ 内存使用正常")
            return True
        else:
            print("✗ 内存使用率过高")
            return False
    except Exception as e:
        print(f"✗ 无法检查内存: {e}")
        return False

def check_network():
    """检查网络连接"""
    print("\n网络检查:")
    try:
        # 尝试连接Google DNS
        socket.setdefaulttimeout(3)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        print("✓ 网络连接正常")
        return True
    except Exception as e:
        print(f"✗ 网络连接失败: {e}")
        return False

def check_cpu_usage():
    """检查CPU使用情况"""
    print("\nCPU使用率:")
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        print(f"当前CPU使用率: {cpu_percent}%")
        if cpu_percent < 90:
            print("✓ CPU使用正常")
            return True
        else:
            print("✗ CPU使用率过高")
            return False
    except Exception as e:
        print(f"✗ 无法检查CPU: {e}")
        return False

def check_common_packages():
    """检查常用包"""
    print("\n常用包检查:")
    packages = ['numpy', 'pandas', 'requests']
    results = []
    for package in packages:
        try:
            __import__(package)
            print(f"✓ {package} 已安装")
            results.append(True)
        except ImportError:
            print(f"✗ {package} 未安装")
            results.append(False)
    return all(results)

def check_time_sync():
    """检查时间同步"""
    print("\n时间同步检查:")
    try:
        current_time = datetime.datetime.now()
        print(f"当前系统时间: {current_time}")
        # 简单检查时间是否在合理范围内
        if current_time.year >= 2020:
            print("✓ 系统时间正常")
            return True
        else:
            print("✗ 系统时间异常")
            return False
    except Exception as e:
        print(f"✗ 无法检查时间: {e}")
        return False

def main():
    """主函数，执行所有检查"""
    print("=" * 50)
    print("环境自检工具")
    print("=" * 50)
    
    results = []
    
    # 执行各项检查
    results.append(("Python版本", check_python_version()))
    check_system_info()
    results.append(("磁盘空间", check_disk_space()))
    results.append(("内存", check_memory()))
    results.append(("网络连接", check_network()))
    results.append(("CPU使用", check_cpu_usage()))
    results.append(("常用包", check_common_packages()))
    results.append(("时间同步", check_time_sync()))
    
    # 总结
    print("\n" + "=" * 50)
    print("自检结果汇总:")
    print("=" * 50)
    
    all_passed = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    print("=" * 50)
    if all_passed:
        print("✓ 所有检查通过！环境正常。")
    else:
        print("✗ 部分检查未通过，请根据上述提示进行修复。")
    print("=" * 50)

if __name__ == "__main__":
    # 需要安装psutil库: pip install psutil
    try:
        import psutil
        main()
    except ImportError:
        print("请安装psutil库: pip install psutil")
        print("正在使用基本检查模式...")
        
        print("=" * 50)
        print("环境自检工具 (基本模式)")
        print("=" * 50)
        
        check_python_version()
        check_system_info()
        
        print("\n由于缺少psutil库，以下高级检查无法执行:")
        print("- 磁盘空间检查")
        print("- 内存检查")
        print("- CPU使用率检查")
        print("- 网络检查")
        
        check_common_packages()
        check_time_sync()
        
        print("\n建议安装psutil库以获得完整的环境检查功能:")
        print("pip install psutil")