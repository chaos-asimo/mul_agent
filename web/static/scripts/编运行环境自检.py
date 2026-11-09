import sys
import platform
import importlib
import json
from datetime import datetime


def check_python_version():
    """检查Python版本"""
    version = sys.version
    version_tuple = sys.version_info
    is_3_8_plus = version_tuple >= (3, 8)
    return {
        "version": version,
        "major": version_tuple.major,
        "minor": version_tuple.minor,
        "micro": version_tuple.micro,
        "is_3_8_plus": is_3_8_plus
    }


def check_platform():
    """检查操作系统平台信息"""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "architecture": platform.architecture(),
        "python_implementation": platform.python_implementation(),
        "node": platform.node()
    }


def check_disk_space(path="/"):
    """检查指定路径的磁盘空间"""
    try:
        import shutil
        total, used, free = shutil.disk_usage(path)
        return {
            "path": path,
            "total_bytes": total,
            "used_bytes": used,
            "free_bytes": free,
            "total_gb": round(total / (1024 ** 3), 2),
            "used_gb": round(used / (1024 ** 3), 2),
            "free_gb": round(free / (1024 ** 3), 2),
            "free_percent": round(free / total * 100, 2) if total > 0 else 0
        }
    except Exception as e:
        return {"error": str(e)}


def check_memory():
    """检查内存使用情况"""
    try:
        import psutil
        memory = psutil.virtual_memory()
        return {
            "total_bytes": memory.total,
            "available_bytes": memory.available,
            "used_bytes": memory.used,
            "total_gb": round(memory.total / (1024 ** 3), 2),
            "available_gb": round(memory.available / (1024 ** 3), 2),
            "used_gb": round(memory.used / (1024 ** 3), 2),
            "percent_used": memory.percent
        }
    except ImportError:
        try:
            # 备用方案：从/proc/meminfo读取（Linux）
            import re
            meminfo = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    match = re.match(r"(\w+):\s+(\d+)\s+kB", line)
                    if match:
                        meminfo[match.group(1)] = int(match.group(2)) * 1024  # 转为字节
            
            total = meminfo.get("MemTotal", 0)
            free = meminfo.get("MemFree", 0)
            available = meminfo.get("MemAvailable", free)
            used = total - available
            
            return {
                "total_bytes": total,
                "available_bytes": available,
                "used_bytes": used,
                "total_gb": round(total / (1024 ** 3), 2),
                "available_gb": round(available / (1024 ** 3), 2),
                "used_gb": round(used / (1024 ** 3), 2),
                "percent_used": round(used / total * 100, 2) if total > 0 else 0,
                "note": "psutil not available, used /proc/meminfo"
            }
        except Exception as e:
            return {"error": f"Cannot read memory info: {e}"}


def check_cpu_info():
    """检查CPU信息"""
    try:
        import psutil
        cpu_count = psutil.cpu_count(logical=True)
        cpu_percent = psutil.cpu_percent(interval=0.1)
        return {
            "logical_cores": cpu_count,
            "physical_cores": psutil.cpu_count(logical=False),
            "current_percent": cpu_percent,
            "freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
        }
    except ImportError:
        return {
            "logical_cores": None,
            "physical_cores": None,
            "note": "psutil not available"
        }


def check_installed_packages(packages=None):
    """检查指定Python包是否已安装"""
    if packages is None:
        # 默认检查一些常用包
        packages = [
            "requests", "numpy", "pandas", "flask", "django",
            "matplotlib", "scipy", "pillow", "sqlalchemy", "pytest"
        ]
    
    results = {}
    for pkg in packages:
        try:
            importlib.import_module(pkg)
            try:
                version = importlib.metadata.version(pkg)
                results[pkg] = {"installed": True, "version": version}
            except importlib.metadata.PackageNotFoundError:
                results[pkg] = {"installed": True, "version": "unknown"}
        except ImportError:
            results[pkg] = {"installed": False, "version": None}
    
    return results


def check_network_connectivity():
    """检查网络连通性"""
    results = {
        "dns_resolution": False,
        "google_ping": False,
        "cloudflare_ping": False
    }
    
    try:
        import socket
        # 测试DNS解析
        socket.gethostbyname("www.google.com")
        results["dns_resolution"] = True
    except Exception:
        pass
    
    try:
        import urllib.request
        # 测试Google连接
        req = urllib.request.Request("https://www.google.com", method="HEAD")
        req.add_header("User-Agent", "EnvironmentCheck/1.0")
        urllib.request.urlopen(req, timeout=5)
        results["google_ping"] = True
    except Exception:
        pass
    
    try:
        import urllib.request
        # 测试Cloudflare连接
        req = urllib.request.Request("https://www.cloudflare.com", method="HEAD")
        req.add_header("User-Agent", "EnvironmentCheck/1.0")
        urllib.request.urlopen(req, timeout=5)
        results["cloudflare_ping"] = True
    except Exception:
        pass
    
    return results


def check_file_permissions():
    """检查当前用户的基本文件权限"""
    temp_dir = "/tmp" if sys.platform != "win32" else "C:\\Windows\\Temp"
    test_file = f"{temp_dir}/env_check_test_{datetime.now().timestamp()}.txt"
    
    results = {
        "can_write_to_temp": False,
        "can_read_current_dir": False,
        "current_working_directory": None
    }
    
    results["current_working_directory"] = os.getcwd() if "os" in dir() else None
    
    try:
        # 检查当前目录可读
        os.listdir(".")
        results["can_read_current_dir"] = True
    except Exception:
        pass
    
    try:
        # 检查临时目录可写
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        results["can_write_to_temp"] = True
    except Exception:
        pass
    
    return results


def run_self_check():
    """运行完整的环境自检"""
    import os
    
    print("=" * 60)
    print("       Python 运行环境自检报告")
    print("=" * 60)
    print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    # 1. Python版本
    print("\n[1] Python 版本信息:")
    py_info = check_python_version()
    print(f"    版本: {py_info['version']}")
    print(f"    是否 >= 3.8: {'是' if py_info['is_3_8_plus'] else '否'}")
    
    # 2. 平台信息
    print("\n[2] 系统平台信息:")
    plat_info = check_platform()
    print(f"    操作系统: {plat_info['system']} {plat_info['release']}")
    print(f"    架构: {plat_info['machine']}")
    print(f"    Python实现: {plat_info['python_implementation']}")
    
    # 3. CPU信息
    print("\n[3] CPU 信息:")
    cpu_info = check_cpu_info()
    print(f"    逻辑核心数: {cpu_info.get('logical_cores', 'N/A')}")
    print(f"    物理核心数: {cpu_info.get('physical_cores', 'N/A')}")
    if cpu_info.get('freq'):
        print(f"    CPU频率: {cpu_info['freq']}")
    
    # 4. 内存信息
    print("\n[4] 内存使用情况:")
    mem_info = check_memory()
    if "error" not in mem_info:
        print(f"    总内存: {mem_info['total_gb']} GB")
        print(f"    已用: {mem_info['used_gb']} GB ({mem_info['percent_used']}%)")
        print(f"    可用: {mem_info['available_gb']} GB")
    else:
        print(f"    错误: {mem_info['error']}")
    
    # 5. 磁盘空间
    print("\n[5] 磁盘空间 (/):")
    disk_info = check_disk_space("/")
    if "error" not in disk_info:
        print(f"    总空间: {disk_info['total_gb']} GB")
        print(f"    已用: {disk_info['used_gb']} GB")
        print(f"    可用: {disk_info['free_gb']} GB ({disk_info['free_percent']}%)")
    else:
        print(f"    错误: {disk_info['error']}")
    
    # 6. 文件权限
    print("\n[6] 文件权限检查:")
    perm_info = check_file_permissions()
    print(f"    当前工作目录: {perm_info.get('current_working_directory', 'N/A')}")
    print(f"    可读取当前目录: {'是' if perm_info.get('can_read_current_dir') else '否'}")
    print(f"    可写入临时目录: {'是' if perm_info.get('can_write_to_temp') else '否'}")
    
    # 7. 网络连通性
    print("\n[7] 网络连通性:")
    net_info = check_network_connectivity()
    print(f"    DNS解析: {'正常' if net_info['dns_resolution'] else '异常'}")
    print(f"    Google连接: {'正常' if net_info['google_ping'] else '异常'}")
    print(f"    Cloudflare连接: {'正常' if net_info['cloudflare_ping'] else '异常'}")
    
    # 8. 常用包安装状态
    print("\n[8] 常用Python包安装状态:")
    pkg_info = check_installed_packages()
    installed_count = sum(1 for v in pkg_info.values() if v["installed"])
    total_count = len(pkg_info)
    for pkg, info in pkg_info.items():
        status = f"{info['version']}" if info["installed"] else "未安装"
        print(f"    {pkg}: {status}")
    print(f"    已安装: {installed_count}/{total_count}")
    
    # 总结
    print("\n" + "=" * 60)
    print("       自检完成")
    print("=" * 60)
    
    return {
        "python_version": py_info,
        "platform": plat_info,
        "cpu": cpu_info,
        "memory": mem_info,
        "disk": disk_info,
        "permissions": perm_info,
        "network": net_info,
        "packages": pkg_info
    }


if __name__ == "__main__":
    result = run_self_check()
    
    # 输出JSON格式的结果（方便程序解析）
    print("\n[JSON格式结果]")
    print(json.dumps(result, indent=2, default=str))