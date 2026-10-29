"""
minilang 词法层的类型定义。

lexer.py 生产 Token，parser.py 消费 Token，双方只依赖这里定义的类型。
"""

from enum import Enum, auto
from dataclasses import dataclass


class TokenType(Enum):
    """Token 的所有可能类型。"""

    # 单字符：读到即产出，无需 peek
    LEFT_PAREN = auto()    # (
    RIGHT_PAREN = auto()   # )
    LEFT_BRACE = auto()    # {
    RIGHT_BRACE = auto()   # }
    COMMA = auto()         # ,
    SEMICOLON = auto()     # ;
    PLUS = auto()          # +
    MINUS = auto()         # -
    STAR = auto()          # *
    SLASH = auto()         # /

    # 一或两字符：需要最长匹配，读到第一个后 peek 下一个
    EQUAL = auto()         # =
    EQUAL_EQUAL = auto()   # ==
    BANG = auto()          # !
    BANG_EQUAL = auto()    # !=
    LESS = auto()          # <
    GREATER = auto()       # >

    # 字面量：需要循环读取，IDENTIFIER 读完后查 KEYWORDS
    IDENTIFIER = auto()    # 标识符，如 x、fib、my_var
    NUMBER = auto()        # 整数字面量，如 42、0

    # 关键字
    # 没有 PRINT：print 是注入全局作用域的内置函数，文法里就是普通 IDENT，可被遮蔽
    LET = auto()           # let
    FUN = auto()           # fun
    IF = auto()            # if
    ELSE = auto()          # else
    WHILE = auto()         # while
    RETURN = auto()        # return
    TRUE = auto()          # true
    FALSE = auto()         # false

    # 结束标记：源码读完后追加，parser 靠它判断输入结束
    EOF = auto()


# 关键字表：标识符读完后查表，命中则升级类型。
# 关键字和标识符词法上同形，必须先读完整单词再查表，
# 所以 ifx 是一个标识符，不是 if + x。
KEYWORDS = {
    "let": TokenType.LET,
    "fun": TokenType.FUN,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "return": TokenType.RETURN,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
}


@dataclass
class Token:
    """词法分析器的输出单元，也是语法分析器的输入单元。"""

    type: TokenType      # 类型，parser 主要看它做分派
    lexeme: str          # 源码原始文本，报错时显示“实际遇到什么”
    literal: object      # 字面量值：NUMBER 是 int，TRUE/FALSE 是 bool，其余为 None
    line: int            # 所在行号，报错时用

    def __repr__(self):
        # 只打类型名、原始文本和行号，避免默认 repr 带出 literal=None
        return f"Token({self.type.name}, {self.lexeme!r}, line={self.line})"