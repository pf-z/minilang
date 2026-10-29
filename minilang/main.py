"""
minilang 命令行入口。

负责三件事：
  1. 把 lexer → parser → interpreter 串成流水线（run 函数）
  2. 提供交互式 REPL（repl 函数）
  3. 解析命令行参数、读取文件、决定退出码（main 函数）

本文件不实现任何语言逻辑，只做调度。
"""

import sys
from typing import List

from .ast_printer import AstPrinter
from .lexer import Lexer
from .parser import Parser
from .interpreter import Interpreter


def run(source: str, show_ast: bool = False) -> int:
    """执行一段源码，返回退出码（0 成功，1 失败）。

    这是非交互场景的完整流水线，三个阶段顺序执行，
    每个阶段出错就打印错误并提前返回，不进入下一阶段。

    以 `let x = 1; print(x);` 为例：
      Lexer 产出 Token 列表 → 无词法错误，继续
      Parser 产出 AST 和空错误列表 → 无语法错误，继续
      Interpreter 执行，print 输出 1 → 返回 0
    """
    # 第一阶段：词法分析。非法字符收集在 lexer.errors 里，不中断扫描。
    lexer = Lexer(source)
    tokens = lexer.scan_tokens()
    if lexer.errors:
        for e in lexer.errors:
            print(e, file=sys.stderr)
        # 词法有错就不进入解析：残缺的 Token 流只会产生误导性的语法错误
        return 1

    # 第二阶段：语法分析。错误恢复在语句级做，一次能报多条。
    parser = Parser(tokens)
    statements, parse_errors = parser.parse()
    if parse_errors:
        for e in parse_errors:
            print(e, file=sys.stderr)
        # 语法有错就不执行：AST 可能只包含部分语句，执行结果不可信
        return 1

    # --ast：只打印语法树，不执行。用于调试 parser。
    if show_ast:
        printer = AstPrinter()
        print(printer.print_statements(statements))
        return 0

    # 第三阶段：执行。运行时错误是抛出式的，一旦发生立即中断。
    interpreter = Interpreter()
    try:
        interpreter.interpret(statements)
    except RuntimeError as e:
        print(f"运行时错误: {e}", file=sys.stderr)
        return 1
    return 0


def repl():
    """交互式 REPL，逐行读取、解析、执行。

    与 run 的关键区别：interpreter 实例在循环外创建，跨行复用。
    所以上一行 let x = 1; 定义的 x，下一行 print(x); 还能用。
    每行独立做词法和语法分析，出错只影响当前行，循环继续。
    """
    # 解释器只创建一次，全局环境跨行保留
    interpreter = Interpreter()
    print("minilang REPL（Ctrl-D 退出）")
    while True:
        try:
            line = input("mini> ")
        except EOFError:
            # Ctrl-D 触发，打印换行让终端提示符回到行首
            print()
            break

        # 空行或纯空白行跳过，不报"期望表达式"
        if not line.strip():
            continue

        # 每行独立做词法分析，错误只影响当前行
        lexer = Lexer(line)
        tokens = lexer.scan_tokens()
        if lexer.errors:
            for e in lexer.errors:
                print(e, file=sys.stderr)
            continue

        # 每行独立做语法分析
        parser = Parser(tokens)
        statements, parse_errors = parser.parse()
        if parse_errors:
            for e in parse_errors:
                print(e, file=sys.stderr)
            continue

        # 执行。这里不 return，出错后循环继续，用户可以改一行重试。
        try:
            interpreter.interpret(statements)
        except RuntimeError as e:
            print(f"运行时错误: {e}", file=sys.stderr)


def main(argv: List[str] = None):
    """解析命令行参数，决定进入 REPL 还是执行文件。

    argv 默认取 sys.argv[1:]，允许测试时传入构造的参数列表。
    """
    if argv is None:
        argv = sys.argv[1:]

    # --ast 是标志，不是位置参数。先摘出来，剩下的才是文件路径。
    # 这样 `python main.py --ast examples/fib.mini` 和
    # `python main.py examples/fib.mini --ast` 都能工作。
    show_ast = "--ast" in argv
    args = [a for a in argv if a != "--ast"]

    # 没有文件参数就进 REPL
    if not args:
        repl()
        return

    # 取第一个位置参数作为文件路径，多余的参数忽略
    path = args[0]
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        # 文件不存在、无权限、编码错误都落在这里
        print(f"无法读取文件 {path}: {e}", file=sys.stderr)
        sys.exit(1)

    # run 返回退出码，直接传给 sys.exit，让 shell 能判断成功与否
    code = run(source, show_ast=show_ast)
    sys.exit(code)


# 支持 `python -m minilang` 和 `python main.py` 两种入口
if __name__ == "__main__":
    main()