import subprocess
import sys

def install_reportlab():
    """
    安装reportlab库
    如果已经安装，则跳过安装步骤
    """
    try:
        import reportlab
        print(f"reportlab已经安装，版本: {reportlab.Version}")
    except ImportError:
        print("reportlab未安装，正在安装...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "reportlab"])
            print("reportlab安装成功！")
        except subprocess.CalledProcessError as e:
            print(f"安装失败: {e}")
            sys.exit(1)

if __name__ == "__main__":
    install_reportlab()