"""
minilang AST 调试打印器。

把语法树以缩进形式输出，用于 --ast 选项和测试。
只负责展示，不参与执行：它不关心语义，只关心树的形状。
"""

from typing import List

from . import ast_nodes as ast


class AstPrinter:
    """递归打印 AST，每个节点占一行或多行，子节点缩进。"""

    def print_node(self, node, indent: int = 0) -> str:
        """把单个节点及其子树转成缩进字符串。

        indent 是当前节点的缩进层数，每层两个空格。
        返回的字符串可能包含换行，子节点由递归调用负责缩进。
        """
        pad = "  " * indent

        # 叶子节点：一行就能表达完
        if isinstance(node, ast.Literal):
            # !r 让字符串带引号、布尔显示 True/False，避免 42 和 '42' 混淆
            return f"{pad}Literal({node.value!r})"
        if isinstance(node, ast.Var):
            return f"{pad}Var({node.name})"

        # 单子节点：先打自己的标签，再换行递归打子节点
        if isinstance(node, ast.Assign):
            return f"{pad}Assign({node.name})\n" + self.print_node(node.value, indent + 1)
        if isinstance(node, ast.Unary):
            return f"{pad}Unary({node.op})\n" + self.print_node(node.right, indent + 1)

        # 双子节点：左右各一行，缩进相同，靠 op 区分是哪种运算
        if isinstance(node, ast.Binary):
            return (
                f"{pad}Binary({node.op})\n"
                + self.print_node(node.left, indent + 1)
                + "\n"
                + self.print_node(node.right, indent + 1)
            )

        # Call 有两个变长部分：callee 一个，arguments 多个。
        # 用 callee: / args: 两个子标题区分，避免歧义。
        if isinstance(node, ast.Call):
            lines = [f"{pad}Call", f"{pad}  callee:"]
            lines.append(self.print_node(node.callee, indent + 2))
            lines.append(f"{pad}  args:")
            for a in node.arguments:
                lines.append(self.print_node(a, indent + 2))
            return "\n".join(lines)

        # ExprStmt 包一个表达式，表达式单独缩进一行
        if isinstance(node, ast.ExprStmt):
            return f"{pad}ExprStmt\n" + self.print_node(node.expression, indent + 1)

        # VarDecl 的 initializer 可选，let x; 时没有下一行
        if isinstance(node, ast.VarDecl):
            s = f"{pad}VarDecl({node.name})"
            if node.initializer is not None:
                s += "\n" + self.print_node(node.initializer, indent + 1)
            return s

        # Block 的语句列表：每条语句一行，缩进相同
        if isinstance(node, ast.Block):
            lines = [f"{pad}Block"]
            for s in node.statements:
                lines.append(self.print_node(s, indent + 1))
            return "\n".join(lines)

        # If 有三个部分：cond 必有，then 必有，else 可选。
        # 用 cond: / then: / else: 子标题区分，比裸缩进更易读。
        if isinstance(node, ast.IfStmt):
            lines = [f"{pad}If", f"{pad}  cond:"]
            lines.append(self.print_node(node.condition, indent + 2))
            lines.append(f"{pad}  then:")
            lines.append(self.print_node(node.then_branch, indent + 2))
            if node.else_branch is not None:
                lines.append(f"{pad}  else:")
                lines.append(self.print_node(node.else_branch, indent + 2))
            return "\n".join(lines)

        # While 和 If 结构类似，但没有 else
        if isinstance(node, ast.WhileStmt):
            lines = [f"{pad}While", f"{pad}  cond:"]
            lines.append(self.print_node(node.condition, indent + 2))
            lines.append(f"{pad}  body:")
            lines.append(self.print_node(node.body, indent + 2))
            return "\n".join(lines)

        # FunctionDecl 的 params 直接打在标签里，body 单独缩进一行
        if isinstance(node, ast.FunctionDecl):
            lines = [f"{pad}FunDecl({node.name}, params={node.params})"]
            lines.append(self.print_node(node.body, indent + 1))
            return "\n".join(lines)

        # Return 的 value 可选，return; 时没有下一行
        if isinstance(node, ast.ReturnStmt):
            s = f"{pad}Return"
            if node.value is not None:
                s += "\n" + self.print_node(node.value, indent + 1)
            return s

        # 兜底：新增节点类型忘了加分支时，打印出来而不是静默失败
        return f"{pad}<unknown {type(node).__name__}>"

    def print_statements(self, statements: List[ast.Stmt]) -> str:
        """打印整个语句列表，每条语句一行（多行节点内部自己换行）。"""
        return "\n".join(self.print_node(s) for s in statements)