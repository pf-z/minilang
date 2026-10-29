"""
minilang 抽象语法树（AST）节点定义。

parser.py 构造这些节点，interpreter.py 和 ast_printer.py 消费它们。

区分表达式和语句的一条实用判据：能不能填进 `let y = ___;` 的下划线。
能填的是 Expr，不能填的是 Stmt。比如 `let y = x;` 合法，说明 Var 是表达式；
`let y = let x = 1;` 不合法，说明 VarDecl 是语句。
"""

from dataclasses import dataclass
from typing import Any, List, Optional


class Expr:
    """表达式基类。求值产生一个值，所以能出现在 `let y = ___;` 的右边。"""
    pass


class Stmt:
    """语句基类。执行产生副作用，没有值，不能出现在 `let y = ___;` 的右边。"""
    pass


# ---------- 表达式节点 ----------

@dataclass
class Literal(Expr):
    """字面量。value 已经是 Python 的 int/bool。

    `let y = 42;` 和 `let y = true;` 都合法，所以它是表达式。
    """
    value: Any


@dataclass
class Unary(Expr):
    """一元运算。op 是运算符字符串 '!' 或 '-'。

    `-x` 求值得到 x 的相反数，`!x` 求值得到布尔取反，
    都能写进 `let y = -x;`，所以是表达式。
    """
    op: str
    right: Expr


@dataclass
class Binary(Expr):
    """二元运算。op 是运算符字符串。

    `1 + 2 * 3` 构造出 Binary('+', Literal(1), Binary('*', Literal(2), Literal(3)))。
    乘法的子树更深，这就是优先级在 AST 里的体现，不需要额外的优先级数字。
    """
    left: Expr
    op: str
    right: Expr


@dataclass
class Var(Expr):
    """变量引用。name 是变量名字符串。

    `let y = x;` 合法，因为 x 求值得到它当前绑定的值。
    """
    name: str


@dataclass
class Assign(Expr):
    """赋值表达式。求值结果是赋进去的值。

    `a = b = 1` 构造出 Assign('a', Assign('b', Literal(1)))，右边递归所以右结合。
    它能写进 `let y = (a = 1);`，y 得到 1，所以是表达式而不是语句。
    副作用（修改环境）和值（右边的值）在这里共存，但分类看的是有没有值。
    """
    name: str
    value: Expr


@dataclass
class Call(Expr):
    """函数调用。callee 是表达式而不是名字，所以支持 f(1)(2)。

    `f(1)(2)` 构造出 Call(Call(Var('f'), [Literal(1)]), [Literal(2)])：
    先求值 f(1) 得到某个函数，再对它求值 (2)。callee 写成 str 就表达不了这种嵌套。
    `let y = f(1);` 合法，y 得到返回值，所以是表达式。
    """
    callee: Expr
    arguments: List[Expr]


# ---------- 语句节点 ----------

@dataclass
class ExprStmt(Stmt):
    """表达式语句。求值后丢弃结果，只为副作用。

    `print(x);` 里的 print(x) 是 Call 表达式，加分号后包成 ExprStmt。
    求值产生打印副作用，返回值 nil 被丢弃。`let y = print(x);` 不合法，
    因为加分号后整个东西是语句，不能出现在 = 右边。
    """
    expression: Expr


@dataclass
class VarDecl(Stmt):
    """变量声明。initializer 可选，let x; 时为 None，解释器绑定为 nil。

    `let x = 1;` 没有值，`let y = let x = 1;` 不合法，所以是语句。
    """
    name: str
    initializer: Optional[Expr]


@dataclass
class Block(Stmt):
    """块。解释器执行时创建新作用域。

    `{ let x = 1; print(x); }` 按顺序执行两条语句，执行完丢弃作用域。
    它没有值，不能写 `let y = { ... };`，所以是语句。
    """
    statements: List[Stmt]


@dataclass
class IfStmt(Stmt):
    """if 语句。else_branch 可选，没有 else 时为 None。

    `if (x < 3) { print(1); } else { print(2); }` 执行后没有值，
    不能写 `let y = if (x) { 1; };`（Rust 可以，minilang 不行）。
    分支体是单条 Stmt，多条语句就写成 Block。
    """
    condition: Expr
    then_branch: Stmt
    else_branch: Optional[Stmt]


@dataclass
class WhileStmt(Stmt):
    """while 语句。body 是单条语句（可以是 Block）。

    `while (i < 10) { i = i + 1; }` 执行后没有值，作用是重复执行循环体。
    body 是单条 Stmt，要放多条就写 Block。
    """
    condition: Expr
    body: Stmt


@dataclass
class FunctionDecl(Stmt):
    """函数声明。params 是参数名字符串列表，body 一定是 Block。

    `fun add(a, b) { return a + b; }` 执行后没有值，
    作用是往环境里绑定一个 MiniFunction。函数名在定义时就绑定，
    所以函数体内能引用自身，递归才能工作。
    """
    name: str
    params: List[str]
    body: Block


@dataclass
class ReturnStmt(Stmt):
    """return 语句。value 可选，return; 时为 None。

    `return x + 1;` 没有"返回值给外层表达式"这回事，
    它的值通过 ReturnSignal 异常带到函数调用处，不是表达式求值的结果。
    """
    value: Optional[Expr]