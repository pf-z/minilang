"""
minilang 树遍历解释器。

输入：parser 产出的 AST 语句列表。
输出：执行副作用（print 输出），运行时错误以 RuntimeError 抛出。

整体结构是两条递归路径加一个环境指针：
  - execute(stmt)  走语句，不返回值，负责副作用
  - evaluate(expr) 走表达式，返回一个值，负责求值
  - self.environment 指向当前作用域，是解释器唯一的可变状态

两条路径互相调用：execute 处理 VarDecl 时要 evaluate 初始化表达式；
evaluate 处理 Call 时触发 MiniFunction.call，又回到 execute 执行函数体。

函数调用通过 MiniCallable 接口抽象，内置 print 和用户函数统一处理。
return 用 ReturnSignal 异常实现，可从任意嵌套深度直接跳到函数调用处。
"""

from typing import Any, List

from . import ast_nodes as ast
from .environment import Environment


class ReturnSignal(Exception):
    """return 语句的信号，携带返回值向上抛。

    为什么用异常而不是返回码：return 可能出现在任意深的嵌套里
    （while 里套 if 里套 return），用异常可以一步跳到 MiniFunction.call，
    中间的 Block、IfStmt、WhileStmt 都不需要检查"是否该返回了"。

    MiniFunction.call 捕获它并取出 value 作为函数返回值；
    如果它冒泡到 Interpreter.interpret，说明 return 在函数外，转成运行时错误。
    """
    def __init__(self, value: Any):
        self.value = value


class MiniCallable:
    """可调用对象的抽象基类。内置函数和用户函数都实现这两个方法。

    有了这个接口，evaluate 的 Call 分支不需要区分"这是 print 还是用户函数"，
    统一检查 isinstance(callee, MiniCallable)、统一检查参数个数、统一调 call。
    """

    def call(self, interpreter: "Interpreter", arguments: List[Any]) -> Any:
        """执行调用，返回调用结果。

        传入 interpreter 是为了让函数体执行时能访问 evaluate/execute_block，
        也为了用 interpreter.stringify 做格式化。
        """
        raise NotImplementedError

    def arity(self) -> int:
        """返回期望的参数个数。evaluate 的 Call 分支用它检查实参个数。"""
        raise NotImplementedError


class PrintFunction(MiniCallable):
    """内置函数 print。接收一个参数，打印后返回 nil。"""

    def arity(self) -> int:
        return 1

    def call(self, interpreter: "Interpreter", arguments: List[Any]) -> Any:
        # 用 interpreter.stringify 统一格式化：None → "nil"，True → "true"，
        # 而不是 Python 默认的 None → "None"、True → "True"
        print(interpreter.stringify(arguments[0]))
        return None   # nil

    def __repr__(self):
        # 让错误信息里显示可读名字，而不是 <__main__.PrintFunction object at 0x...>
        return "<内置函数 print>"


class MiniFunction(MiniCallable):
    """用户定义的函数。保存声明节点和定义时的环境（闭包）。"""

    def __init__(self, declaration: ast.FunctionDecl, closure: Environment):
        self.declaration = declaration
        # 定义时的环境。调用时以它为父环境新建作用域，
        # 所以函数体能访问定义处的变量，这就是闭包。
        # 保存引用而不是拷贝，是为了让多次调用共享同一个环境：
        # makeCounter 返回的 increment 两次调用改的是同一个 count。
        self.closure = closure

    def arity(self) -> int:
        return len(self.declaration.params)

    def call(self, interpreter: "Interpreter", arguments: List[Any]) -> Any:
        # 新环境，父环境是定义环境。参数绑定在这层，函数体局部变量也在这层。
        # 每次调用都新建，所以递归调用之间参数互不干扰。
        env = Environment(self.closure)

        # 按位置绑定参数。参数名来自声明，值来自实参。
        for name, value in zip(self.declaration.params, arguments):
            env.define(name, value)

        try:
            # 切换到 env 执行函数体。execute_block 的 finally 保证
            # 无论正常结束还是抛 ReturnSignal，interpreter.environment 都会恢复。
            interpreter.execute_block(self.declaration.body.statements, env)
        except ReturnSignal as r:
            # return 把值带到这里，正常返回
            return r.value

        # 没有执行到 return，函数返回 nil
        return None

    def __repr__(self):
        return f"<函数 {self.declaration.name}>"


class Interpreter:
    def __init__(self):
        self.globals = Environment()
        # print 是注入全局作用域的内置函数，不是关键字，所以可被用户变量遮蔽
        self.globals.define("print", PrintFunction())
        # 当前环境指针。execute_block 执行块时会临时切换，执行完恢复。
        # 这是解释器唯一的可变状态，理解它的切换就理解了作用域。
        self.environment = self.globals

    # ---------- 执行 ----------

    def interpret(self, statements: List[ast.Stmt]):
        """执行整个语句列表。ReturnSignal 冒泡到这里说明 return 在函数外。

        正常执行时 ReturnSignal 在 MiniFunction.call 里就被捕获了，
        不会到这里。能冒泡上来只可能是顶层写了 return，比如 `return 1;`。
        """
        try:
            for stmt in statements:
                self.execute(stmt)
        except ReturnSignal:
            raise RuntimeError("return 只能在函数内部使用")

    def execute(self, stmt: ast.Stmt):
        """执行一条语句，不返回值。按 Stmt 子类分派。

        每个分支都以 return 结尾，所以同一时刻只处理一种语句。
        最后的 raise 是兜底：新增 Stmt 子类但忘了加分支时能立刻发现。
        """

        if isinstance(stmt, ast.ExprStmt):
            # 求值表达式，丢弃结果，只留副作用（如 print）。
            # 这就是"表达式语句"的语义：值不要，只要它做了什么。
            self.evaluate(stmt.expression)
            return

        if isinstance(stmt, ast.VarDecl):
            # 没有初始化表达式时绑定 nil：let x; 等价于 let x = nil;
            value = None
            if stmt.initializer is not None:
                value = self.evaluate(stmt.initializer)
            # define 只写当前层，不查父层，所以内层 let 遮蔽外层同名变量
            self.environment.define(stmt.name, value)
            return

        if isinstance(stmt, ast.Block):
            # 新建子环境，父环境是当前环境。出块后环境恢复，块内变量不可见。
            # 用 execute_block 而不是直接 for 循环，是为了让环境切换有统一的入口。
            self.execute_block(stmt.statements, Environment(self.environment))
            return

        if isinstance(stmt, ast.IfStmt):
            # 条件求值后用 truthy 判断，只有 nil 和 false 为假
            if self.truthy(self.evaluate(stmt.condition)):
                self.execute(stmt.then_branch)
            elif stmt.else_branch is not None:
                self.execute(stmt.else_branch)
            return

        if isinstance(stmt, ast.WhileStmt):
            # 每轮重新求值条件，所以条件里的变量变化能影响循环
            while self.truthy(self.evaluate(stmt.condition)):
                self.execute(stmt.body)
            return

        if isinstance(stmt, ast.FunctionDecl):
            # 闭包捕获当前环境作为定义环境。
            # 函数名在定义时就绑定到当前环境，所以函数体内引用自身时
            # 沿环境链能找到这个 MiniFunction，递归才能工作。
            function = MiniFunction(stmt, self.environment)
            self.environment.define(stmt.name, function)
            return

        if isinstance(stmt, ast.ReturnStmt):
            value = None
            if stmt.value is not None:
                value = self.evaluate(stmt.value)
            # 用异常跳出当前函数的所有嵌套语句，直达 MiniFunction.call。
            # 不返回值给外层表达式，而是通过异常把值带到调用处。
            raise ReturnSignal(value)

        raise RuntimeError(f"未知语句类型: {type(stmt).__name__}")

    def execute_block(self, statements: List[ast.Stmt], env: Environment):
        """在指定环境中执行一组语句，执行完恢复原环境。

        这是环境切换的唯一入口。块和函数调用都走这里，
        所以作用域隔离的行为在两种场景下完全一致。

        finally 是必需的：如果函数体抛 ReturnSignal 或运行时错误，
        self.environment 必须恢复，否则后续执行会用错环境。
        没有 finally 的话，异常穿过时 self.environment 会停在 env 上。
        """
        previous = self.environment
        try:
            self.environment = env
            for stmt in statements:
                self.execute(stmt)
        finally:
            self.environment = previous

    # ---------- 求值 ----------

    def evaluate(self, expr: ast.Expr) -> Any:
        """求值一个表达式，返回它的值。按 Expr 子类分派。

        与 execute 的区别：execute 处理"做什么"，evaluate 处理"等于什么"。
        evaluate 一定有返回值（可以是 None/nil），execute 不返回。
        """

        if isinstance(expr, ast.Literal):
            # value 已经是 int/bool，lexer 在 number() 里就转好了，直接返回
            return expr.value

        if isinstance(expr, ast.Var):
            # 沿环境链向上找，找不到抛"未定义变量"。
            # 查找方向是当前层 → 父层 → 全局，所以内层能看见外层，反之不行。
            return self.environment.get(expr.name)

        if isinstance(expr, ast.Assign):
            value = self.evaluate(expr.value)
            # 沿链找已存在的绑定并修改，不会新建变量。
            # 这和 define 的关键区别：assign 不遮蔽，只修改找到的那个。
            self.environment.assign(expr.name, value)
            # 赋值表达式的值就是右边的值，所以 a = b = 1 能右结合，
            # 也能写 let y = (a = 1); y 得到 1。
            return value

        if isinstance(expr, ast.Unary):
            right = self.evaluate(expr.right)
            if expr.op == "!":
                # 逻辑取反，用 truthy 统一真值判断
                return not self.truthy(right)
            if expr.op == "-":
                # 算术取反，要求严格整数
                self.require_int(right, "一元 '-'")
                return -right
            raise RuntimeError(f"未知一元运算符: {expr.op}")

        if isinstance(expr, ast.Binary):
            # 二元运算逻辑多，单独抽到 eval_binary
            return self.eval_binary(expr)

        if isinstance(expr, ast.Call):
            # 三步顺序不能反：先求 callee，再求参数，最后调用。
            callee = self.evaluate(expr.callee)
            args = [self.evaluate(a) for a in expr.arguments]

            # callee 必须实现 MiniCallable，否则是"调用非函数值"
            if not isinstance(callee, MiniCallable):
                raise RuntimeError(f"不能调用非函数值: {self.stringify(callee)}")

            # 参数个数在调用前检查，所以函数体不会因参数缺失而出错
            if len(args) != callee.arity():
                raise RuntimeError(
                    f"{callee} 期望 {callee.arity()} 个参数，实际 {len(args)} 个"
                )

            # 统一调用接口。print 和用户函数在这里没有区别。
            return callee.call(self, args)

        raise RuntimeError(f"未知表达式类型: {type(expr).__name__}")

    def eval_binary(self, expr: ast.Binary) -> Any:
        """求值二元运算。先求左右，再按 op 分派。

        左右都先求值，所以求值顺序是固定的：先左后右。
        这意味着 `f() + g()` 先调 f 再调 g，副作用顺序确定。
        """
        left = self.evaluate(expr.left)
        right = self.evaluate(expr.right)
        op = expr.op

        # == 和 != 可比较任意值，不要求整数。
        # 用 Python 的 == 直接比较，所以函数对象、nil 也能比较。
        if op == "==":
            return left == right
        if op == "!=":
            return left != right

        # 其余运算符要求严格整数。bool 虽然是 int 子类，但不参与算术，
        # 所以 true + 1 会报错而不是得到 2。
        if op == "+":
            self.require_int(left, "'+'")
            self.require_int(right, "'+'")
            return left + right
        if op == "-":
            self.require_int(left, "'-'")
            self.require_int(right, "'-'")
            return left - right
        if op == "*":
            self.require_int(left, "'*'")
            self.require_int(right, "'*'")
            return left * right
        if op == "/":
            self.require_int(left, "'/'")
            self.require_int(right, "'/'")
            # 除零在运算前检查，避免 Python 的 ZeroDivisionError 泄漏成实现细节
            if right == 0:
                raise RuntimeError("除以零")
            # 整数除法，向负无穷取整（Python 的 // 语义）
            return left // right
        if op == "<":
            self.require_int(left, "'<'")
            self.require_int(right, "'<'")
            return left < right
        if op == ">":
            self.require_int(left, "'>'")
            self.require_int(right, "'>'")
            return left > right

        raise RuntimeError(f"未知二元运算符: {op}")

    # ---------- 辅助 ----------

    def require_int(self, value: Any, where: str):
        """要求 value 严格是 int。

        用 type(value) is not int 而不是 isinstance：
        Python 里 bool 是 int 的子类，isinstance(True, int) 返回 True。
        如果允许布尔参与算术，true + 1 会得到 2，这不是语言设计想要的。
        where 是出错位置描述，如 "'+'"、"一元 '-'"，拼进错误信息里。
        """
        if type(value) is not int:
            raise RuntimeError(f"{where} 需要整数，实际得到: {self.stringify(value)}")

    def truthy(self, value: Any) -> bool:
        """真值判断：只有 nil 和 false 为假，0 为真。

        这个选择让 `if (0) {...}` 进入分支，和 Python 的 0 为假不同，
        和 C 的 0 为假也不同，是 minilang 自己的语义。
        """
        if value is None or value is False:
            return False
        return True

    def stringify(self, value: Any) -> str:
        """把运行时值格式化成用户可见的字符串。

        用户不应该看到 Python 的 None/True/False，
        所以统一转成 nil/true/false。其他值用 str，整数就是十进制。
        """
        if value is None:
            return "nil"
        if value is True:
            return "true"
        if value is False:
            return "false"
        return str(value)