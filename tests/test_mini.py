import io
import unittest
from contextlib import redirect_stdout

from minilang.lexer import Lexer
from minilang.parser import Parser
from minilang.interpreter import Interpreter
from minilang.tokens import TokenType
from minilang import ast_nodes as ast


def token_types(source):
    lexer = Lexer(source)
    tokens = lexer.scan_tokens()
    assert not lexer.errors, lexer.errors
    return [t.type for t in tokens]


def parse(source):
    lexer = Lexer(source)
    tokens = lexer.scan_tokens()
    assert not lexer.errors, lexer.errors
    parser = Parser(tokens)
    stmts, errors = parser.parse()
    assert not errors, errors
    return stmts


def run_source(source):
    buf = io.StringIO()
    with redirect_stdout(buf):
        lexer = Lexer(source)
        tokens = lexer.scan_tokens()
        assert not lexer.errors, lexer.errors
        parser = Parser(tokens)
        stmts, errors = parser.parse()
        assert not errors, errors
        Interpreter().interpret(stmts)
    return buf.getvalue()


class TestLexer(unittest.TestCase):
    def test_basic_tokens(self):
        types = token_types("let x = 42;")
        self.assertEqual(
            types,
            [
                TokenType.LET,
                TokenType.IDENTIFIER,
                TokenType.EQUAL,
                TokenType.NUMBER,
                TokenType.SEMICOLON,
                TokenType.EOF,
            ],
        )

    def test_two_char_operators(self):
        types = token_types("== != < > = !")
        self.assertEqual(
            types,
            [
                TokenType.EQUAL_EQUAL,
                TokenType.BANG_EQUAL,
                TokenType.LESS,
                TokenType.GREATER,
                TokenType.EQUAL,
                TokenType.BANG,
                TokenType.EOF,
            ],
        )

    def test_comment(self):
        types = token_types("let x = 1; // 注释\nlet y = 2;")
        self.assertEqual(types.count(TokenType.LET), 2)

    def test_keywords_vs_identifiers(self):
        types = token_types("let ifx = 1;")
        self.assertEqual(
            types,
            [
                TokenType.LET,
                TokenType.IDENTIFIER,
                TokenType.EQUAL,
                TokenType.NUMBER,
                TokenType.SEMICOLON,
                TokenType.EOF,
            ],
        )


class TestParser(unittest.TestCase):
    def test_precedence(self):
        stmts = parse("1 + 2 * 3;")
        expr = stmts[0].expression
        self.assertIsInstance(expr, ast.Binary)
        self.assertEqual(expr.op, "+")
        self.assertIsInstance(expr.right, ast.Binary)
        self.assertEqual(expr.right.op, "*")

    def test_left_associativity(self):
        stmts = parse("1 - 2 - 3;")
        expr = stmts[0].expression
        self.assertEqual(expr.op, "-")
        self.assertIsInstance(expr.left, ast.Binary)
        self.assertEqual(expr.left.op, "-")

    def test_right_associativity_of_assignment(self):
        stmts = parse("a = b = 1;")
        expr = stmts[0].expression
        self.assertIsInstance(expr, ast.Assign)
        self.assertEqual(expr.name, "a")
        self.assertIsInstance(expr.value, ast.Assign)
        self.assertEqual(expr.value.name, "b")

    def test_if_else(self):
        stmts = parse("if (1 < 2) { print(1); } else { print(2); }")
        self.assertIsInstance(stmts[0], ast.IfStmt)
        self.assertIsNotNone(stmts[0].else_branch)

    def test_fun_declaration_parses(self):
        stmts = parse("fun add(a, b) { return a + b; }")
        self.assertIsInstance(stmts[0], ast.FunctionDecl)
        self.assertEqual(stmts[0].name, "add")
        self.assertEqual(stmts[0].params, ["a", "b"])
        self.assertIsInstance(stmts[0].body, ast.Block)
        self.assertEqual(len(stmts[0].body.statements), 1)
        self.assertIsInstance(stmts[0].body.statements[0], ast.ReturnStmt)


class TestInterpreter(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(run_source("print(1 + 2 * 3);"), "7\n")

    def test_variable_and_assignment(self):
        self.assertEqual(run_source("let x = 1; x = x + 1; print(x);"), "2\n")

    def test_if_else(self):
        src = """
        let x = 1;
        if (x < 2) { print(10); } else { print(20); }
        """
        self.assertEqual(run_source(src), "10\n")

    def test_while(self):
        src = """
        let i = 0;
        let s = 0;
        while (i < 5) {
          s = s + i;
          i = i + 1;
        }
        print(s);
        """
        self.assertEqual(run_source(src), "10\n")

    def test_function_and_recursion(self):
        src = """
        fun fib(n) {
          if (n < 2) { return n; }
          return fib(n - 1) + fib(n - 2);
        }
        print(fib(10));
        """
        self.assertEqual(run_source(src), "55\n")

    def test_closure(self):
        src = """
        fun makeCounter() {
          let count = 0;
          fun increment() {
            count = count + 1;
            return count;
          }
          return increment;
        }
        let c = makeCounter();
        print(c());
        print(c());
        print(c());
        """
        self.assertEqual(run_source(src), "1\n2\n3\n")

    def test_block_scope(self):
        src = """
        let x = 1;
        {
          let x = 2;
          print(x);
        }
        print(x);
        """
        self.assertEqual(run_source(src), "2\n1\n")

    def test_runtime_error_undefined_variable(self):
        with self.assertRaises(RuntimeError):
            run_source("print(y);")

    def test_runtime_error_divide_by_zero(self):
        with self.assertRaises(RuntimeError):
            run_source("print(1 / 0);")


if __name__ == "__main__":
    unittest.main()