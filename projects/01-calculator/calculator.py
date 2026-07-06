def calculate(a, operator, b):
    if operator == "+":
        return a + b
    if operator == "-":
        return a - b
    if operator == "*":
        return a * b
    if operator == "/" and b != 0:
        return a / b
    raise ValueError("올바른 연산을 입력하세요")


print(calculate(12, "*", 3))
