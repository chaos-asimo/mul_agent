def fibonacci(n):
    """
    计算斐波那契数列的前n项
    
    参数:
    n (int): 需要计算的斐波那契数列的项数
    
    返回:
    list: 包含斐波那契数列前n项的列表
    """
    if n <= 0:
        return []
    if n == 1:
        return [0]
    
    # 初始化斐波那契数列的前两项
    fib_sequence = [0, 1]
    
    # 计算剩余的项
    for i in range(2, n):
        next_value = fib_sequence[i-1] + fib_sequence[i-2]
        fib_sequence.append(next_value)
    
    return fib_sequence


def main():
    # 计算斐波那契数列的前20项
    n = 20
    result = fibonacci(n)
    
    print(f"斐波那契数列的前{n}项为：")
    print(result)


if __name__ == "__main__":
    main()