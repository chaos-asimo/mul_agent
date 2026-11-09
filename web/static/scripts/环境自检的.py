import platform
import sys
import os
import json
from datetime import datetime

def check_python_version():
    """检查Python版本"""
    version_info = sys.version_info
    return {
        "version": sys.version,
        "major": version_info.major,
        "minor": version_info.minor,
        "micro": version_info.micro,
        "status": "OK" if version_info.major >= 3 and version_info.minor >= 8 else "WARNING"
    }

def check_system_info():
    """检查系统信息"""
    return {
        "os_name": platform.system(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "node": platform.node()
    }

def check_memory_info():
    """检查内存信息"""
    try:
        import psutil
        memory = psutil.virtual_memory()
        return {
            "total_gb": round(memory.total / (1024**3), 2),
            "available_gb": round(memory.available / (1024**3), 2),
            "used_percent": memory.percent,
            "status": "OK" if memory.percent < 90 else "WARNING"
        }
    except ImportError:
        return {
            "note": "psutil library not installed, cannot check detailed memory info"
        }

def check_disk_info():
    """检查磁盘信息"""
    try:
        import psutil
        disk = psutil.disk_usage('/')
        return {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "used_percent": disk.percent,
            "status": "OK" if disk.percent < 90 else "WARNING"
        }
    except ImportError:
        return {
            "note": "psutil library not installed, cannot check detailed disk info"
        }
    except Exception as e:
        return {
            "error": f"Could not read disk info: {str(e)}"
        }

def check_installed_packages():
    """检查已安装的常用包"""
    packages_to_check = [
        'numpy', 'pandas', 'requests', 'flask', 'django',
        'matplotlib', 'scipy', 'sklearn', 'tensorflow', 'torch'
    ]
    
    installed = {}
    for pkg_name in packages_to_check:
        try:
            module = __import__(pkg_name)
            version = getattr(module, '__version__', 'Unknown')
            installed[pkg_name] = {
                "installed": True,
                "version": version
            }
        except ImportError:
            installed[pkg_name] = {
                "installed": False,
                "version": None
            }
    
    return installed

def check_environment_variables():
    """检查重要的环境变量"""
    important_vars = [
        'PATH', 'HOME', 'USER', 'LANG', 'PYTHONPATH'
    ]
    
    env_vars = {}
    for var in important_vars:
        value = os.environ.get(var, 'Not set')
        # 为了安全，不显示完整PATH等敏感变量
        if var in ['PATH', 'PYTHONPATH'] and value != 'Not set':
            env_vars[var] = f"Set ({len(value)} characters)"
        else:
            env_vars[var] = value if value != 'Not set' else 'Not set'
    
    return env_vars

def generate_report():
    """生成完整的系统自检报告"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "python_version": check_python_version(),
        "system_info": check_system_info(),
        "memory_info": check_memory_info(),
        "disk_info": check_disk_info(),
        "installed_packages": check_installed_packages(),
        "environment_variables": check_environment_variables()
    }
    
    return report

def print_report(report):
    """格式化打印报告"""
    print("=" * 60)
    print("         系统环境自检报告")
    print("=" * 60)
    print(f"检查时间: {report['timestamp']}")
    print()
    
    # Python版本
    print("--- Python 版本 ---")
    py_ver = report['python_version']
    print(f"版本: {py_ver['version']}")
    print(f"状态: {py_ver['status']}")
    print()
    
    # 系统信息
    print("--- 系统信息 ---")
    sys_info = report['system_info']
    for key, value in sys_info.items():
        print(f"{key}: {value}")
    print()
    
    # 内存信息
    print("--- 内存信息 ---")
    mem_info = report['memory_info']
    if 'total_gb' in mem_info:
        print(f"总内存: {mem_info['total_gb']} GB")
        print(f"可用内存: {mem_info['available_gb']} GB")
        print(f"已用百分比: {mem_info['used_percent']}%")
        print(f"状态: {mem_info.get('status', 'N/A')}")
    else:
        print(f"注: {mem_info.get('note', '无法获取内存信息')}")
    print()
    
    # 磁盘信息
    print("--- 磁盘信息 ---")
    disk_info = report['disk_info']
    if 'total_gb' in disk_info:
        print(f"总磁盘: {disk_info['total_gb']} GB")
        print(f"已用磁盘: {disk_info['used_gb']} GB")
        print(f"可用磁盘: {disk_info['free_gb']} GB")
        print(f"已用百分比: {disk_info['used_percent']}%")
        print(f"状态: {disk_info.get('status', 'N/A')}")
    else:
        print(f"注: {disk_info.get('note', '无法获取磁盘信息')}")
        if 'error' in disk_info:
            print(f"错误: {disk_info['error']}")
    print()
    
    # 已安装的包
    print("--- 常用包安装状态 ---")
    packages = report['installed_packages']
    for pkg_name, info in packages.items():
        status = "✓ 已安装" if info['installed'] else "✗ 未安装"
        version_str = f" (版本: {info['version']})" if info['version'] else ""
        print(f"{pkg_name:15s} {status}{version_str}")
    print()
    
    # 环境变量
    print("--- 重要环境变量 ---")
    env_vars = report['environment_variables']
    for var, value in env_vars.items():
        print(f"{var}: {value}")
    print()
    
    print("=" * 60)
    print("自检完成")
    print("=" * 60)

if __name__ == "__main__":
    report = generate_report()
    print_report(report)
    
    # 同时保存JSON格式的报告
    try:
        with open('system_report.json', 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print("\n报告已保存到: system_report.json")
    except Exception as e:
        print(f"\n保存报告失败: {e}")