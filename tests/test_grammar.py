"""
按 docs/grammar.ebnf 的产生式组织的文法测试。

每个测试类的 docstring 引用对应产生式，正例断言 AST 结构，
反例断言 parse() 产生错误。这个文件保证 docs/grammar.ebnf
和 parser.py 同步：改文法先改 EBNF，再补测试，最后改 parser.py。
"""

import unittest

from minilang.lexer import Lexer
from minilang.parser import Parser
from minilang import ast_nodes as ast


def parse(source):
    """走 lexer + parser，断言无词法错误，返回 (statements, errors)。"""
    lexer = Lexer(source)
    tokens = lexer.scan_tokens()
    assert not lexer.errors, f"词法错误: {lexer.errors}"
    parser = Parser(tokens)
    return parser.parse()


def assert_parses(source):
    """断言 source 能成功解析，返回 statements。"""
    statements, errors = parse(source)
    assert not errors, f"期望成功解析，实际错误: {errors}"
    return statements


def assert_fails(source):
    """断言 source 解析失败，返回错误列表。"""
    statements, errors = parse(source)
    assert errors, f"期望解析失败，实际成功: {statements}"
    return errors


class TestProgram(unittest.TestCase):
    """program → declaration* EOF"""

    def test_empty_program(self):
        # declaration* 允许 0 次
        self.assertEqual(assert_parses(""), [])

    def test_multiple_declarations(self):
        stmts = assert_parses("let x = 1; let y = 2;")
        self.assertEqual(len(stmts), 2)
        self.assertIsInstance(stmts[0], ast.VarDecl)
        self.assertIsInstance(stmts[1], ast.VarDecl)


class TestDeclaration(unittest.TestCase):
    """declaration → funDecl | varDecl | statement"""

    def test_fun_declaration(self):
        stmts = assert_parses("fun f() {}")
        self.assertIsInstance(stmts[0], ast.FunctionDecl)

    def test_var_declaration(self):
        stmts = assert_parses("let x = 1;")
        self.assertIsInstance(stmts[0], ast.VarDecl)

    def test_statement_as_declaration(self):
        stmts = assert_parses("print(1);")
        self.assertIsInstance(stmts[0], ast.ExprStmt)

    def test_missing_semicolon_after_var(self):
        # varDecl 规则要求 ";"
        assert_fails("let x = 1")


class TestFunDecl(unittest.TestCase):
    """funDecl → "fun" IDENT "(" params? ")" block"""

    def test_no_params(self):
        stmts = assert_parses("fun f() {}")
        self.assertEqual(stmts[0].params, [])

    def test_one_param(self):
        stmts = assert_parses("fun f(a) {}")
        self.assertEqual(stmts[0].params, ["a"])

    def test_multiple_params(self):
        # params → IDENT ("," IDENT)*
        stmts = assert_parses("fun f(a, b, c) {}")
        self.assertEqual(stmts[0].params, ["a", "b", "c"])

    def test_missing_param_name(self):
        # fun f(,) 里逗号后缺 IDENT
        assert_fails("fun f(,) {}")

    def test_trailing_comma_in_params(self):
        # params → IDENT ("," IDENT)*，末尾逗号不构成完整单元
        assert_fails("fun f(a,) {}")

    def test_missing_body(self):
        # funDecl 要求 block
        assert_fails("fun f()")


class TestVarDecl(unittest.TestCase):
    """varDecl → "let" IDENT ("=" expression)? ";" """

    def test_with_initializer(self):
        stmts = assert_parses("let x = 1;")
        self.assertIsNotNone(stmts[0].initializer)

    def test_without_initializer(self):
        # ("=" expression)? 允许省略
        stmts = assert_parses("let x;")
        self.assertIsNone(stmts[0].initializer)

    def test_missing_name(self):
        assert_fails("let = 1;")

    def test_missing_expression_after_equal(self):
        # let x = ; 里 = 后缺 expression
        assert_fails("let x = ;")


class TestStatement(unittest.TestCase):
    """statement → exprStmt | ifStmt | whileStmt | returnStmt | block"""

    def test_expr_stmt(self):
        stmts = assert_parses("1 + 2;")
        self.assertIsInstance(stmts[0], ast.ExprStmt)

    def test_if_stmt(self):
        stmts = assert_parses("if (true) {}")
        self.assertIsInstance(stmts[0], ast.IfStmt)

    def test_while_stmt(self):
        stmts = assert_parses("while (true) {}")
        self.assertIsInstance(stmts[0], ast.WhileStmt)

    def test_return_stmt(self):
        stmts = assert_parses("fun f() { return 1; }")
        self.assertIsInstance(stmts[0].body.statements[0], ast.ReturnStmt)

    def test_block(self):
        stmts = assert_parses("{}")
        self.assertIsInstance(stmts[0], ast.Block)

    def test_empty_statement_fails(self):
        # statement 不接受裸分号，exprStmt 要求 expression
        assert_fails(";")


class TestExprStmt(unittest.TestCase):
    """exprStmt → expression ";" """

    def test_expression_with_semicolon(self):
        stmts = assert_parses("1;")
        self.assertIsInstance(stmts[0], ast.ExprStmt)

    def test_missing_semicolon(self):
        assert_fails("1")


class TestIfStmt(unittest.TestCase):
    """ifStmt → "if" "(" expression ")" statement ("else" statement)? """

    def test_without_else(self):
        stmts = assert_parses("if (true) {}")
        self.assertIsNone(stmts[0].else_branch)

    def test_with_else(self):
        # ("else" statement)? 允许有 else
        stmts = assert_parses("if (true) {} else {}")
        self.assertIsNotNone(stmts[0].else_branch)

    def test_missing_parens(self):
        # ifStmt 要求 "(" expression ")"
        assert_fails("if true {}")

    def test_missing_then_branch(self):
        assert_fails("if (true)")

    def test_dangling_else_binds_to_nearest_if(self):
        # else 绑定到内层 if，外层的 else_branch 为 None
        stmts = assert_parses("if (true) if (false) {} else {}")
        outer = stmts[0]
        self.assertIsNone(outer.else_branch)
        self.assertIsNotNone(outer.then_branch.else_branch)


class TestWhileStmt(unittest.TestCase):
    """whileStmt → "while" "(" expression ")" statement"""

    def test_with_block_body(self):
        stmts = assert_parses("while (true) {}")
        self.assertIsInstance(stmts[0].body, ast.Block)

    def test_with_single_statement_body(self):
        # body 是单条 statement，可以不是 block
        stmts = assert_parses("while (true) print(1);")
        self.assertIsInstance(stmts[0].body, ast.ExprStmt)

    def test_missing_parens(self):
        assert_fails("while true {}")

    def test_missing_body(self):
        assert_fails("while (true)")


class TestReturnStmt(unittest.TestCase):
    """returnStmt → "return" expression? ";" """

    def test_with_value(self):
        stmts = assert_parses("fun f() { return 1; }")
        self.assertIsNotNone(stmts[0].body.statements[0].value)

    def test_without_value(self):
        # expression? 允许省略
        stmts = assert_parses("fun f() { return; }")
        self.assertIsNone(stmts[0].body.statements[0].value)

    def test_missing_semicolon(self):
        # return 1 后紧跟 }，consume(SEMICOLON) 失败
        assert_fails("fun f() { return 1 }")


class TestBlock(unittest.TestCase):
    """block → "{" declaration* "}" """

    def test_empty_block(self):
        stmts = assert_parses("{}")
        self.assertEqual(stmts[0].statements, [])

    def test_block_contains_declarations(self):
        # declaration* 里可以有 let，所以块内能声明变量
        stmts = assert_parses("{ let x = 1; }")
        self.assertIsInstance(stmts[0].statements[0], ast.VarDecl)

    def test_block_contains_fun_declaration(self):
        stmts = assert_parses("{ fun f() {} }")
        self.assertIsInstance(stmts[0].statements[0], ast.FunctionDecl)

    def test_missing_right_brace(self):
        assert_fails("{ let x = 1;")


class TestAssignment(unittest.TestCase):
    """assignment → IDENT "=" assignment | equality"""

    def test_simple_assignment(self):
        stmts = assert_parses("x = 1;")
        expr = stmts[0].expression
        self.assertIsInstance(expr, ast.Assign)
        self.assertEqual(expr.name, "x")

    def test_right_associative(self):
        # a = b = 1 解析成 a = (b = 1)
        stmts = assert_parses("a = b = 1;")
        expr = stmts[0].expression
        self.assertIsInstance(expr, ast.Assign)
        self.assertEqual(expr.name, "a")
        self.assertIsInstance(expr.value, ast.Assign)
        self.assertEqual(expr.value.name, "b")

    def test_assignment_target_must_be_var(self):
        # 1 = 2 左边不是 IDENT，不匹配第一条分支
        assert_fails("1 = 2;")


class TestEquality(unittest.TestCase):
    """equality → comparison (("==" | "!=") comparison)*"""

    def test_single_equality(self):
        stmts = assert_parses("a == b;")
        self.assertEqual(stmts[0].expression.op, "==")

    def test_not_equal(self):
        stmts = assert_parses("a != b;")
        self.assertEqual(stmts[0].expression.op, "!=")

    def test_left_associative(self):
        # a == b == c 解析成 (a == b) == c
        stmts = assert_parses("a == b == c;")
        expr = stmts[0].expression
        self.assertIsInstance(expr.left, ast.Binary)
        self.assertEqual(expr.left.op, "==")


class TestComparison(unittest.TestCase):
    """comparison → term (("<" | ">") term)*"""

    def test_less_than(self):
        stmts = assert_parses("a < b;")
        self.assertEqual(stmts[0].expression.op, "<")

    def test_greater_than(self):
        stmts = assert_parses("a > b;")
        self.assertEqual(stmts[0].expression.op, ">")

    def test_left_associative(self):
        # a < b < c 解析成 (a < b) < c
        stmts = assert_parses("a < b < c;")
        self.assertIsInstance(stmts[0].expression.left, ast.Binary)


class TestTerm(unittest.TestCase):
    """term → factor (("+" | "-") factor)*"""

    def test_plus(self):
        stmts = assert_parses("a + b;")
        self.assertEqual(stmts[0].expression.op, "+")

    def test_minus(self):
        stmts = assert_parses("a - b;")
        self.assertEqual(stmts[0].expression.op, "-")

    def test_left_associative(self):
        # a - b - c 解析成 (a - b) - c
        stmts = assert_parses("a - b - c;")
        expr = stmts[0].expression
        self.assertIsInstance(expr.left, ast.Binary)
        self.assertEqual(expr.left.op, "-")

    def test_plus_binds_looser_than_star(self):
        # a + b * c 解析成 a + (b * c)
        stmts = assert_parses("a + b * c;")
        expr = stmts[0].expression
        self.assertEqual(expr.op, "+")
        self.assertIsInstance(expr.right, ast.Binary)
        self.assertEqual(expr.right.op, "*")


class TestFactor(unittest.TestCase):
    """factor → unary (("*" | "/") unary)*"""

    def test_star(self):
        stmts = assert_parses("a * b;")
        self.assertEqual(stmts[0].expression.op, "*")

    def test_slash(self):
        stmts = assert_parses("a / b;")
        self.assertEqual(stmts[0].expression.op, "/")

    def test_left_associative(self):
        # a * b * c 解析成 (a * b) * c
        stmts = assert_parses("a * b * c;")
        self.assertIsInstance(stmts[0].expression.left, ast.Binary)


class TestUnary(unittest.TestCase):
    """unary → ("!" | "-") unary | call"""

    def test_not(self):
        stmts = assert_parses("!a;")
        self.assertIsInstance(stmts[0].expression, ast.Unary)
        self.assertEqual(stmts[0].expression.op, "!")

    def test_negate(self):
        stmts = assert_parses("-a;")
        self.assertEqual(stmts[0].expression.op, "-")

    def test_nested_unary(self):
        # !!a 解析成 !(!a)
        stmts = assert_parses("!!a;")
        outer = stmts[0].expression
        self.assertIsInstance(outer, ast.Unary)
        self.assertIsInstance(outer.right, ast.Unary)

    def test_missing_operand(self):
        # ! 后面缺 unary
        assert_fails("!;")


class TestCall(unittest.TestCase):
    """call → primary ("(" arguments? ")")*"""

    def test_no_arguments(self):
        stmts = assert_parses("f();")
        self.assertIsInstance(stmts[0].expression, ast.Call)
        self.assertEqual(stmts[0].expression.arguments, [])

    def test_one_argument(self):
        stmts = assert_parses("f(1);")
        self.assertEqual(len(stmts[0].expression.arguments), 1)

    def test_multiple_arguments(self):
        # arguments → expression ("," expression)*
        stmts = assert_parses("f(1, 2, 3);")
        self.assertEqual(len(stmts[0].expression.arguments), 3)

    def test_trailing_comma_in_arguments(self):
        # arguments → expression ("," expression)*，末尾逗号不构成完整单元
        assert_fails("f(1,);")

    def test_chained_call(self):
        # f(1)(2) 解析成 (f(1))(2)
        stmts = assert_parses("f(1)(2);")
        outer = stmts[0].expression
        self.assertIsInstance(outer, ast.Call)
        self.assertIsInstance(outer.callee, ast.Call)

    def test_missing_right_paren(self):
        assert_fails("f(1;")


class TestPrimary(unittest.TestCase):
    """primary → NUMBER | "true" | "false" | IDENT | "(" expression ")" """

    def test_number(self):
        stmts = assert_parses("42;")
        self.assertIsInstance(stmts[0].expression, ast.Literal)
        self.assertEqual(stmts[0].expression.value, 42)

    def test_true(self):
        stmts = assert_parses("true;")
        self.assertEqual(stmts[0].expression.value, True)

    def test_false(self):
        stmts = assert_parses("false;")
        self.assertEqual(stmts[0].expression.value, False)

    def test_identifier(self):
        stmts = assert_parses("x;")
        self.assertIsInstance(stmts[0].expression, ast.Var)

    def test_parenthesized(self):
        # (1 + 2) 解析成 Binary，括号本身不产生节点
        stmts = assert_parses("(1 + 2);")
        self.assertIsInstance(stmts[0].expression, ast.Binary)

    def test_parenthesized_changes_precedence(self):
        # (1 + 2) * 3 的根是 *，左子是 +；对比 1 + 2 * 3 的根是 +
        stmts = assert_parses("(1 + 2) * 3;")
        expr = stmts[0].expression
        self.assertEqual(expr.op, "*")
        self.assertIsInstance(expr.left, ast.Binary)
        self.assertEqual(expr.left.op, "+")

    def test_missing_right_paren(self):
        assert_fails("(1 + 2;")

    def test_empty_parens(self):
        # () 里缺 expression
        assert_fails("();")


if __name__ == "__main__":
    unittest.main()