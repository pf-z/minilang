"""
minilang 语法分析器。

输入：lexer 产出的 Token 列表（末尾一定有 EOF）。
输出：(AST 语句列表, 错误消息列表)。

实现方式是递归下降：每个 EBNF 产生式对应一个 parse_* 方法，
方法内部按文法右端的顺序调用工具方法"吃掉"Token。
优先级靠调用层次表达，结合性靠循环（左结合）或递归（右结合）表达。
错误恢复在语句级做 synchronize，一次运行可报告多个语法错误。
"""

from typing import List, Optional, Tuple

from .tokens import Token, TokenType
from . import ast_nodes as ast


class ParseError(Exception):
    """语法错误。consume/primary 抛出，parse() 捕获后做错误恢复。"""
    pass


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.current = 0          # 指向下一个待处理 Token 的下标
        self.errors: List[str] = []

    # ---------- 入口 ----------

    def parse(self) -> Tuple[List[ast.Stmt], List[str]]:
        """解析整个 Token 流，返回 (语句列表, 错误列表)。

        以 `let x = 1 + 2;` 为例，调用链是：
          parse → declaration → var_declaration
                → expression → assignment → equality → comparison → term
                → factor → unary → call → primary（解析 1 和 2）
        每层只做两件事：调下一层拿子节点，再看当前 Token 决定是否继续。

        每条语句独立 try：某条语句语法错误不会阻止后续语句解析。
        错误后调 synchronize() 跳到下一个语句边界。
        """
        statements: List[ast.Stmt] = []
        while not self.is_at_end():
            try:
                statements.append(self.declaration())
            except ParseError as e:
                self.errors.append(str(e))
                self.synchronize()
        return statements, self.errors

    # ---------- 声明 ----------
    # declaration 是 program 和 block 的共同入口：
    # 函数和变量可以出现在顶层，也可以出现在任何块内。

    def declaration(self) -> ast.Stmt:
        """按当前 Token 分派：fun / let / 普通语句。

        `fun f() {...}` → FunctionDecl
        `let x = 1;`    → VarDecl
        `print(1);`     → ExprStmt（落到 statement）
        """
        if self.match(TokenType.FUN):
            return self.fun_declaration()
        if self.match(TokenType.LET):
            return self.var_declaration()
        return self.statement()

    def fun_declaration(self) -> ast.FunctionDecl:
        """funDecl → "fun" IDENT "(" params? ")" block

        例：`fun add(a, b) { return a + b; }`
          返回 FunctionDecl('add', ['a','b'],
                           Block([ReturnStmt(Binary(+, Var('a'), Var('b')))]))。

        注意 block() 的约定是左花括号已被吃掉，
        所以这里先 consume(LEFT_BRACE) 再调 block()。
        """
        name = self.consume(TokenType.IDENTIFIER, "期望函数名")
        self.consume(TokenType.LEFT_PAREN, "期望 '('")
        params: List[str] = []
        if not self.check(TokenType.RIGHT_PAREN):
            # params → IDENT ("," IDENT)*
            # 空参数 fun f() {} 时 check 为真，跳过循环
            while True:
                params.append(self.consume(TokenType.IDENTIFIER, "期望参数名").lexeme)
                if not self.match(TokenType.COMMA):
                    break
        self.consume(TokenType.RIGHT_PAREN, "期望 ')'")
        self.consume(TokenType.LEFT_BRACE, "期望 '{'")
        body = self.block()
        return ast.FunctionDecl(name.lexeme, params, body)

    def var_declaration(self) -> ast.VarDecl:
        """varDecl → "let" IDENT ("=" expression)? ";"

        `let x = 1;` → VarDecl('x', Literal(1))
        `let x;`     → VarDecl('x', None)，解释器绑定为 nil
        """
        name = self.consume(TokenType.IDENTIFIER, "期望变量名")
        init: Optional[ast.Expr] = None
        if self.match(TokenType.EQUAL):
            init = self.expression()
        self.consume(TokenType.SEMICOLON, "期望 ';'")
        return ast.VarDecl(name.lexeme, init)

    # ---------- 语句 ----------

    def statement(self) -> ast.Stmt:
        """按当前 Token 分派到五种语句之一。

        if / while / return 各走对应函数；{ 走 block；
        其余一律按"表达式加分号"处理，落到 expression_statement。
        所以 print(x);、x = 2;、f(1); 都走最后一条路径。

        注意花括号：statement 里 match(LEFT_BRACE) 后调 block()，
        和 fun_declaration 里一样，遵守"左花括号已吃掉"的约定。
        """
        if self.match(TokenType.IF):
            return self.if_statement()
        if self.match(TokenType.WHILE):
            return self.while_statement()
        if self.match(TokenType.RETURN):
            return self.return_statement()
        if self.match(TokenType.LEFT_BRACE):
            return self.block()
        return self.expression_statement()

    def block(self) -> ast.Block:
        """block → "{" declaration* "}"

        `{ let x = 1; print(x); }`
        → Block([VarDecl('x', Literal(1)),
                 ExprStmt(Call(Var('print'), [Var('x')]))])

        进入时左花括号已被吃掉，循环直到遇到右花括号或 EOF。
        用 declaration() 而不是 statement()，所以块内可以直接写 let 和 fun。
        """
        statements: List[ast.Stmt] = []
        while not self.check(TokenType.RIGHT_BRACE) and not self.is_at_end():
            statements.append(self.declaration())
        self.consume(TokenType.RIGHT_BRACE, "期望 '}'")
        return ast.Block(statements)

    def if_statement(self) -> ast.IfStmt:
        """ifStmt → "if" "(" expression ")" statement ("else" statement)?

        `if (x < 3) { print(1); } else { print(2); }`
        → IfStmt(Binary(<, Var('x'), Literal(3)),
                 Block([ExprStmt(Call(...print(1)...))]),
                 Block([ExprStmt(Call(...print(2)...))]))

        悬空 else 绑定到最近的 if，因为内层 if_statement()
        会先消费掉 else，外层 match(ELSE) 就失败了——递归下降的天然行为。
        """
        self.consume(TokenType.LEFT_PAREN, "期望 '('")
        cond = self.expression()
        self.consume(TokenType.RIGHT_PAREN, "期望 ')'")
        then_b = self.statement()
        else_b: Optional[ast.Stmt] = None
        if self.match(TokenType.ELSE):
            else_b = self.statement()
        return ast.IfStmt(cond, then_b, else_b)

    def while_statement(self) -> ast.WhileStmt:
        """whileStmt → "while" "(" expression ")" statement

        `while (i < 10) { i = i + 1; }`
        → WhileStmt(Binary(<, Var('i'), Literal(10)),
                    Block([ExprStmt(Assign('i', Binary(+, Var('i'), Literal(1))))]))

        body 是单条 statement：多条语句写块，单条语句可省略花括号。
        """
        self.consume(TokenType.LEFT_PAREN, "期望 '('")
        cond = self.expression()
        self.consume(TokenType.RIGHT_PAREN, "期望 ')'")
        body = self.statement()
        return ast.WhileStmt(cond, body)

    def return_statement(self) -> ast.ReturnStmt:
        """returnStmt → "return" expression? ";"

        `return x + 1;` → ReturnStmt(Binary(+, Var('x'), Literal(1)))
        `return;`       → ReturnStmt(None)

        下一个 Token 是分号则无返回值，否则解析表达式。
        """
        value: Optional[ast.Expr] = None
        if not self.check(TokenType.SEMICOLON):
            value = self.expression()
        self.consume(TokenType.SEMICOLON, "期望 ';'")
        return ast.ReturnStmt(value)

    def expression_statement(self) -> ast.ExprStmt:
        """exprStmt → expression ";"

        `print(x);` → ExprStmt(Call(Var('print'), [Var('x')]))
        `x = 2;`    → ExprStmt(Assign('x', Literal(2)))

        表达式求值有值，ExprStmt 把值丢弃，只留副作用。
        """
        expr = self.expression()
        self.consume(TokenType.SEMICOLON, "期望 ';'")
        return ast.ExprStmt(expr)

    # ---------- 表达式 ----------
    # 层次从低到高：赋值 < 相等 < 比较 < 加减 < 乘除 < 一元 < 调用 < 原子
    # 越靠下的方法绑定越紧，优先级不需要额外的数字表。

    def expression(self) -> ast.Expr:
        """expression → assignment，只是入口转发。

        保留这层是为了和 EBNF 的 expression → assignment 对应，
        也给以后加其他表达式入口（如逗号表达式）留位置。
        """
        return self.assignment()

    def assignment(self) -> ast.Expr:
        """assignment → IDENT "=" assignment | equality

        `a = b = 1` → Assign('a', Assign('b', Literal(1)))
        右边递归调用自身，所以右结合。

        `(x) = 1` 的 expr 也是 Var('x')，当前实现会接受，
        这是入门阶段的宽松；严格实现需要区分裸标识符和括号标识符。
        """
        expr = self.equality()
        if self.match(TokenType.EQUAL):
            value = self.assignment()
            if isinstance(expr, ast.Var):
                return ast.Assign(expr.name, value)
            self.error(self.previous(), "无效的赋值目标")
        return expr

    def equality(self) -> ast.Expr:
        """equality → comparison (("==" | "!=") comparison)*

        `a == b == c` → Binary(Binary(a, ==, b), ==, c)
        while 循环每轮把已有 expr 包进新 Binary 的左边，所以左结合。
        """
        expr = self.comparison()
        while self.match(TokenType.EQUAL_EQUAL, TokenType.BANG_EQUAL):
            op = self.previous().lexeme
            right = self.comparison()
            expr = ast.Binary(expr, op, right)
        return expr

    def comparison(self) -> ast.Expr:
        """comparison → term (("<" | ">") term)*，左结合。

        `1 < 2 < 3` → Binary(Binary(1, <, 2), <, 3)
        """
        expr = self.term()
        while self.match(TokenType.LESS, TokenType.GREATER):
            op = self.previous().lexeme
            right = self.term()
            expr = ast.Binary(expr, op, right)
        return expr

    def term(self) -> ast.Expr:
        """term → factor (("+" | "-") factor)*，左结合。

        `1 - 2 - 3` → Binary(Binary(1, -, 2), -, 3)
        `1 + 2 * 3` 里 factor 先解析出 2 * 3，所以乘法绑定更紧。
        """
        expr = self.factor()
        while self.match(TokenType.PLUS, TokenType.MINUS):
            op = self.previous().lexeme
            right = self.factor()
            expr = ast.Binary(expr, op, right)
        return expr

    def factor(self) -> ast.Expr:
        """factor → unary (("*" | "/") unary)*，左结合。

        `2 * 3 * 4` → Binary(Binary(2, *, 3), *, 4)
        """
        expr = self.unary()
        while self.match(TokenType.STAR, TokenType.SLASH):
            op = self.previous().lexeme
            right = self.unary()
            expr = ast.Binary(expr, op, right)
        return expr

    def unary(self) -> ast.Expr:
        """unary → ("!" | "-") unary | call

        `-x`  → Unary(-, Var('x'))
        `!!a` → Unary(!, Unary(!, Var('a')))
        递归处理连续一元运算符；没有一元运算符时落到 call。
        """
        if self.match(TokenType.BANG, TokenType.MINUS):
            op = self.previous().lexeme
            right = self.unary()
            return ast.Unary(op, right)
        return self.call()

    def call(self) -> ast.Expr:
        """call → primary ("(" arguments? ")")*

        `f(1, x)` → Call(Var('f'), [Literal(1), Var('x')])
        `f(1)(2)` → Call(Call(Var('f'), [Literal(1)]), [Literal(2)])

        用 while 而不是 if，所以支持连续调用：
        第一次循环得到 Call(f, [1])，第二次循环得到 Call(Call(f, [1]), [2])。
        """
        expr = self.primary()
        while self.match(TokenType.LEFT_PAREN):
            args: List[ast.Expr] = []
            if not self.check(TokenType.RIGHT_PAREN):
                # arguments → expression ("," expression)*
                while True:
                    args.append(self.expression())
                    if not self.match(TokenType.COMMA):
                        break
            self.consume(TokenType.RIGHT_PAREN, "期望 ')'")
            expr = ast.Call(expr, args)
        return expr

    def primary(self) -> ast.Expr:
        """primary → NUMBER | "true" | "false" | IDENT | "(" expression ")"

        `42`    → Literal(42)
        `true`  → Literal(True)
        `x`     → Var('x')
        `(1+2)` → Binary(+, Literal(1), Literal(2))（括号只改变解析顺序，不产生节点）

        最底层，不再递归调用其他表达式方法（括号内除外）。
        注意 print 不在这里单独处理：它是 IDENT，解释器运行时
        会从全局环境查到内置的 PrintFunction。
        """
        if self.match(TokenType.FALSE):
            return ast.Literal(False)
        if self.match(TokenType.TRUE):
            return ast.Literal(True)
        if self.match(TokenType.NUMBER):
            # literal 已经是 int，直接用，不需要再转换
            return ast.Literal(self.previous().literal)
        if self.match(TokenType.IDENTIFIER):
            return ast.Var(self.previous().lexeme)
        if self.match(TokenType.LEFT_PAREN):
            expr = self.expression()
            self.consume(TokenType.RIGHT_PAREN, "期望 ')'")
            return expr
        self.error(self.peek(), "期望表达式")
        raise ParseError("不可达")  # self.error 已抛异常，此行仅为类型检查

    # ---------- 工具 ----------
    # 这组方法只被 Parser 自己调用，维护 current 游标。
    # 拆出去没有第二个使用者，留在类里保持文法方法和实现机制的边界清晰。

    def match(self, *types: TokenType) -> bool:
        """当前 Token 匹配任一类型则消耗并返回 True，否则不动返回 False。

        `match(PLUS, MINUS)` 在 `1 + 2` 里看到 + 就吃掉并返回 True；
        在 `1 * 2` 里看到 * 不匹配，current 不动，返回 False。
        """
        for t in types:
            if self.check(t):
                self.advance()
                return True
        return False

    def check(self, t: TokenType) -> bool:
        """当前 Token 是否是指定类型。EOF 处一律返回 False，防止误匹配。"""
        if self.is_at_end():
            return False
        return self.peek().type == t

    def advance(self) -> Token:
        """消耗当前 Token 并返回它。EOF 处不前进，防止越界。"""
        if not self.is_at_end():
            self.current += 1
        return self.previous()

    def is_at_end(self) -> bool:
        """是否已到 Token 流末尾（lexer 保证末尾一定有 EOF 哨兵）。"""
        return self.peek().type == TokenType.EOF

    def peek(self) -> Token:
        """看当前 Token 但不消耗。"""
        return self.tokens[self.current]

    def previous(self) -> Token:
        """看刚被消耗的 Token，用于取 lexeme 或报错定位。

        `consume(NUMBER)` 之后 `previous().literal` 就是那个数字的值。
        """
        return self.tokens[self.current - 1]

    def consume(self, t: TokenType, msg: str) -> Token:
        """当前 Token 类型匹配则消耗并返回，否则抛 ParseError。

        `consume(SEMICOLON, "期望 ';'")` 在 `let x = 1` 缺分号时抛
        "[第 1 行] 解析错误: 期望 ';'（遇到 ''）"，因为 EOF 的 lexeme 是空串。

        msg 是"期望什么"，error() 会补上"实际遇到什么"和行号。
        """
        if self.check(t):
            return self.advance()
        self.error(self.peek(), msg)
        raise ParseError("不可达")  # self.error 已抛异常，此行仅为类型检查

    def error(self, token: Token, msg: str):
        """构造带行号和实际 Token 的 ParseError 并抛出。

        `error(peek(), "期望表达式")` 在 `let x = ;` 里产生
        "[第 1 行] 解析错误: 期望表达式（遇到 ';'）"。
        """
        raise ParseError(f"[第 {token.line} 行] 解析错误: {msg}（遇到 {token.lexeme!r}）")

    def synchronize(self):
        """错误恢复：丢弃 Token 直到下一个语句边界。

        边界有两种：
          - 刚吃掉一个分号：上一条语句结束；
          - 当前 Token 是语句起始关键字：下一条语句开始。

        例：`let x = ; let y = 2;` 第一条语句在 `;` 处报错后，
        synchronize 会前进到 `let`（下一条语句的起点），
        然后 parse() 的循环继续解析 `let y = 2;`，所以 errors 非空
        但 statements 里仍有第二条语句。
        """
        self.advance()
        while not self.is_at_end():
            if self.previous().type == TokenType.SEMICOLON:
                return
            if self.peek().type in (
                TokenType.FUN,
                TokenType.LET,
                TokenType.IF,
                TokenType.WHILE,
                TokenType.RETURN,
            ):
                return
            self.advance()