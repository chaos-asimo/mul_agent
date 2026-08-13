import time

def crazy_output():
    print("疯狂输出开始！")
    for i in range(10):
        print(f"疯狂输出次数: {i + 1}")
        time.sleep(0.5)  # 控制输出速度
    print("疯狂输出结束！")

if __name__ == "__main__":
    crazy_output()