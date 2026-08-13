import subprocess
import sys

# 安装 PyPDF2 库
subprocess.check_call([sys.executable, "-m", "pip", "install", "PyPDF2"])

# 验证安装是否成功
try:
    import PyPDF2
    print("PyPDF2 已成功安装并导入。")
except ImportError:
    print("PyPDF2 安装失败。")