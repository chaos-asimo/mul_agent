import sys
import os

def main():
    """
    主函数：演示如何自行解决常见环境问题（如依赖缺失、路径错误等）
    """
    try:
        # 尝试导入可能未安装的库，如果失败则自行处理
        import requests
    except ImportError:
        print("警告: 'requests' 库未安装。")
        print("正在尝试通过 subprocess 安装 'requests'...")
        try:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
            import requests
            print("成功安装 'requests' 库。")
        except Exception as e:
            print(f"安装失败: {e}")
            print("脚本将继续运行，但某些功能可能受限。")
            requests = None

    try:
        # 检查当前工作目录是否存在，如果不存在则创建
        current_dir = os.getcwd()
        test_dir = os.path.join(current_dir, "test_self_resolved_dir")
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)
            print(f"创建测试目录: {test_dir}")
        else:
            print(f"测试目录已存在: {test_dir}")
        
        # 清理测试目录
        cleanup_dir = os.path.join(test_dir, "clean_me.txt")
        with open(cleanup_dir, 'w') as f:
            f.write("This file will be deleted.")
        
        if os.path.exists(cleanup_dir):
            os.remove(cleanup_dir)
            print(f"成功清理文件: {cleanup_dir}")

        print("\n所有问题已自行解决！")
        
        # 如果 requests 可用，打印一个简单的状态
        if requests:
            print(f"requests 库版本: {requests.__version__}")
        else:
            print("requests 库不可用。")

    except Exception as e:
        print(f"发生未知错误: {e}")
        # 即使出错，也尝试打印一些调试信息
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()