import os
import sys
import platform
import subprocess
import psutil
import datetime
import socket
import uuid

def print_header(title):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")

def print_info(label, value):
    print(f"  {label}: {value}")

def get_hardware_info():
    print_header("硬件信息")
    
    # CPU信息
    try:
        cpu_info = platform.processor()
        cpu_count = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq()
        cpu_per = psutil.cpu_percent(interval=1)
        
        print_info("处理器", cpu_info or "未知")
        print_info("CPU核心数 (逻辑)", cpu_count)
        if cpu_freq:
            print_info("CPU频率 (MHz)", f"{cpu_freq.current:.2f} (当前) / {cpu_freq.max:.2f} (最大)")
        else:
            print_info("CPU频率", "无法获取")
        print_info("CPU使用率", f"{cpu_per}%")
    except Exception as e:
        print(f"  获取CPU信息失败: {e}")

    # 内存信息
    try:
        vm = psutil.virtual_memory()
        print_info("总内存 (GB)", f"{vm.total / (1024**3):.2f}")
        print_info("可用内存 (GB)", f"{vm.available / (1024**3):.2f}")
        print_info("内存使用率", f"{vm.percent}%")
    except Exception as e:
        print(f"  获取内存信息失败: {e}")

    # 磁盘信息
    try:
        disk = psutil.disk_usage('/')
        print_info("磁盘总大小 (GB)", f"{disk.total / (1024**3):.2f}")
        print_info("磁盘可用大小 (GB)", f"{disk.free / (1024**3):.2f}")
        print_info("磁盘使用率", f"{disk.percent}%")
    except Exception as e:
        print(f"  获取磁盘信息失败: {e}")

    # 电池信息 (仅在笔记本电脑上有效)
    try:
        battery = psutil.sensors_battery()
        if battery:
            print_info("电池电量", f"{battery.percent}%")
            print_info("电池状态", "充电中" if battery.power_plugged else "未充电")
        else:
            print_info("电池", "不可用或台式机")
    except Exception:
        print_info("电池", "不可用")

    # 网络接口
    try:
        addrs = socket.gethostbyname_ex(socket.gethostname())
        print_info("主机名", socket.gethostname())
        print_info("IP地址", addrs[2][0] if addrs[2] else "无法获取")
    except Exception as e:
        print(f"  获取网络信息失败: {e}")

def get_software_info():
    print_header("软件信息")
    
    # 操作系统信息
    print_info("操作系统", platform.platform())
    print_info("系统版本", platform.version())
    print_info("系统名称", platform.system())
    print_info("架构", platform.machine())
    print_info("处理器", platform.processor() or "未知")

    # Python信息
    print_info("Python版本", platform.python_version())
    print_info("Python实现", platform.python_implementation())
    print_info("Python路径", sys.executable)
    print_info("工作目录", os.getcwd())
    print_info("系统路径", os.name)

    # 进程信息
    try:
        process = psutil.Process(os.getpid())
        print_info("当前进程ID", os.getpid())
        print_info("当前进程名称", process.name())
        print_info("当前进程状态", process.status())
        print_info("进程创建时间", datetime.datetime.fromtimestamp(process.create_time()).strftime('%Y-%m-%d %H:%M:%S'))
    except Exception as e:
        print(f"  获取进程信息失败: {e}")

    # 环境变量
    try:
        env_vars = list(os.environ.keys())
        print_info("环境变量数量", len(env_vars))
        # 显示几个关键的环境变量
        key_vars = ['PATH', 'HOME', 'USER', 'SHELL', 'PYTHONPATH']
        for var in key_vars:
            val = os.environ.get(var, '未设置')
            if len(val) > 50:
                val = val[:50] + "..."
            print_info(f"  {var}", val)
    except Exception as e:
        print(f"  获取环境变量失败: {e}")

def check_dependencies():
    print_header("依赖库检查")
    
    required_packages = ['psutil']
    installed = []
    missing = []
    
    for pkg in required_packages:
        try:
            __import__(pkg)
            installed.append(pkg)
            print_info(f"✓ {pkg}", "已安装")
        except ImportError:
            missing.append(pkg)
            print_info(f"✗ {pkg}", "未安装")
    
    if missing:
        print(f"\n  请安装缺失的依赖库: pip install {' '.join(missing)}")
    
    return len(missing) == 0

def system_check():
    print_header("系统自检报告")
    print(f"  检查时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  系统标识: {uuid.getnode()}")
    
    # 检查依赖
    deps_ok = check_dependencies()
    
    if not deps_ok:
        print("\n  警告: 缺少必要的依赖库，部分信息可能无法获取")
        # 即使依赖缺失，也尝试获取基本信息
        get_software_info()
        try:
            get_hardware_info()
        except:
            pass
        return
    
    # 获取软硬信息
    get_hardware_info()
    get_software_info()
    
    print_header("自检完成")
    print("  所有检查项已完成。")
    print("  请根据上述信息评估系统状态。")

if __name__ == "__main__":
    # 需要安装 psutil 库: pip install psutil
    try:
        import psutil
    except ImportError:
        print("错误: 需要安装 psutil 库才能运行此脚本")
        print("请运行: pip install psutil")
        sys.exit(1)
    
    system_check()