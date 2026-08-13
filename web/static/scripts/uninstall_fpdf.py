import subprocess
import sys

# 卸载fpdf库
try:
    subprocess.check_call([sys.executable, "-m", "pip", "uninstall", "-y", "fpdf"])
    print("fpdf库已成功卸载。")
except subprocess.CalledProcessError as e:
    print(f"卸载fpdf库时出错: {e}")
except FileNotFoundError:
    print("未找到pip，请确保已安装pip。")