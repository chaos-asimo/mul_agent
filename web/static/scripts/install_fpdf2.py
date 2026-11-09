import subprocess
import sys

def install_fpdf2():
    """安装 fpdf2 库"""
    try:
        # 使用 pip 安装 fpdf2
        subprocess.check_call([sys.executable, "-m", "pip", "install", "fpdf2"])
        print("fpdf2 库安装成功！")
    except subprocess.CalledProcessError as e:
        print(f"安装失败: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    install_fpdf2()