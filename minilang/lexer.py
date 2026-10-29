"""
minilang 词法分析器。

输入：源码字符串（source）
输出：Token 列表（以 EOF 结尾），以及 errors 里收集的词法错误

核心是三个游标：
 - start   记录当前 Token 的起点，add_token 用它切片出 lexeme
 - current 记录扫描位置，scan_token 每次从它这里读字符
 - line    记录当前行号，遇换行递增，Token 和错误都带行号

scan_tokens 循环调用 scan_token，每次读一个字符，根据字符类型分派：
 - 单字符标点直接产出
 - = 和 ! 需要 peek 下一个字符做最长匹配（== / !=）
 - 数字和标识符需要循环读取
 - // 需要跳过整行
 - 空白跳过
 - 换行递增 line
 - 非法字符记入 errors 但继续扫描

读完源码后追加 EOF 哨兵，这是 parser 判断"输入结束"的唯一依据，
没有它 parser 在文件末尾会越界。

词法错误不中断扫描，一次运行能报告所有非法字符。
"""

from typing import List, Optional

from .tokens import Token, TokenType, KEYWORDS


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.start = 0        # 当前 Token 的起始字符下标
        self.current = 0      # 当前扫描到的字符下标
        self.line = 1         # 当前行号，遇 \n 递增
        self.tokens: List[Token] = []
        self.errors: List[str] = []

    # ---------- 主循环 ----------

    def scan_tokens(self) -> List[Token]:
        """扫描整个源码，最后追加 EOF Token 并返回列表。

        每次循环前把 start 对齐到 current，表示"新 Token 从这里开始"。
        scan_token 负责吃掉至少一个字符，所以循环一定前进，不会死循环。
        """
        while not self.is_at_end():
            self.start = self.current   # 每个 Token 从这里开始切
            self.scan_token()
        self.tokens.append(Token(TokenType.EOF, "", None, self.line))
        return self.tokens

    def is_at_end(self) -> bool:
        return self.current >= len(self.source)

    def scan_token(self):
        """读一个字符，决定产出什么 Token。

        分派顺序很重要：先处理单字符标点（最常见、无歧义），
        再处理需要 peek 的 / = !，最后处理需要循环的数字和标识符。
        非法字符走 else，记错误但不中断。
        """
        c = self.advance()

        # 单字符标点：读到即产出，无需 peek。
        # 用字典而不是 if 链，是为了让"字符 → 类型"的映射一目了然，
        # 新增单字符运算符时只加一行。
        single = {
            "(": TokenType.LEFT_PAREN,
            ")": TokenType.RIGHT_PAREN,
            "{": TokenType.LEFT_BRACE,
            "}": TokenType.RIGHT_BRACE,
            ",": TokenType.COMMA,
            ";": TokenType.SEMICOLON,
            "+": TokenType.PLUS,
            "-": TokenType.MINUS,
            "*": TokenType.STAR,
        }
        if c in single:
            self.add_token(single[c])
        elif c == "/":
            # 最长匹配：// 是注释，否则是除号。
            # 注释内容直接丢弃，不产出 Token；循环到 \n 或文件末尾为止。
            if self.match("/"):
                while self.peek() != "\n" and not self.is_at_end():
                    self.advance()
            else:
                self.add_token(TokenType.SLASH)
        elif c == "=":
            # 最长匹配：== 还是 =。
            # match("=") 成功说明下一个字符也是 =，已消耗；否则 current 不动。
            self.add_token(TokenType.EQUAL_EQUAL if self.match("=") else TokenType.EQUAL)
        elif c == "!":
            # 最长匹配：!= 还是 !。
            self.add_token(TokenType.BANG_EQUAL if self.match("=") else TokenType.BANG)
        elif c == "<":
            self.add_token(TokenType.LESS)
        elif c == ">":
            self.add_token(TokenType.GREATER)
        elif c in " \r\t":
            # 空白直接跳过，不产出 Token。
            pass
        elif c == "\n":
            # 换行不产出 Token，只更新行号，供后续 Token 和错误使用。
            self.line += 1
        elif c.isdigit():
            self.number()
        elif c.isalpha() or c == "_":
            # 标识符首字符只能是字母或下划线，不能是数字
            #（否则 42x 会被当成一个标识符，而正确行为是 NUMBER(42) + IDENT(x)）。
            self.identifier()
        else:
            # 非法字符不中断扫描，收集错误继续。
            # 这样一次运行能报告所有非法字符，而不是遇到第一个就停。
            self.errors.append(f"[第 {self.line} 行] 非法字符: {c!r}")

    # ---------- 循环读取 ----------

    def number(self):
        """循环读数字，产出 NUMBER，literal 直接是 int。

        从当前字符（已确认是数字）开始，连续读 digit 直到非数字。
        用 [start, current) 切片拿到完整文本，转成 int 存进 literal，
        parser 构造 Literal 节点时可以直接用，不需要二次转换。
        """
        while self.peek().isdigit():
            self.advance()
        text = self.source[self.start:self.current]
        self.add_token(TokenType.NUMBER, int(text))

    def identifier(self):
        """循环读字母/数字/下划线，读完查 KEYWORDS 决定是否升级为关键字。

        关键字和标识符词法上同形，不能读第一个字符就定类型
        （whilex 不是 while + x）。必须读完整单词再查表：
        命中 KEYWORDS 就把类型换成对应关键字，否则保留 IDENTIFIER。
        """
        while self.peek().isalnum() or self.peek() == "_":
            self.advance()
        text = self.source[self.start:self.current]
        tt = KEYWORDS.get(text, TokenType.IDENTIFIER)
        self.add_token(tt)

    # ---------- 游标操作 ----------

    def match(self, expected: str) -> bool:
        """下一个字符是 expected 则消耗并返回 True，否则不动返回 False。

        这是最长匹配的核心：只在匹配成功时前进。
        = 和 == 的区分完全靠它——match("=") 失败时 current 不变，
        下一个字符留给下一轮 scan_token。
        """
        if self.is_at_end() or self.source[self.current] != expected:
            return False
        self.current += 1
        return True

    def peek(self) -> str:
        """看下一个字符但不消耗。

        到末尾返回 '\\0'，让 while self.peek().isdigit() 这类循环
        自然终止，调用方不必每处都写 not self.is_at_end()。
        '\\0' 既不是数字也不是字母，也不是任何运算符，不会误匹配。
        """
        if self.is_at_end():
            return "\0"
        return self.source[self.current]

    def advance(self) -> str:
        """消耗并返回当前字符。

        调用方保证不在末尾调用：scan_token 在主循环里调用，
        主循环条件已保证 current < len(source)。
        """
        c = self.source[self.current]
        self.current += 1
        return c

    def add_token(self, type_: TokenType, literal: Optional[object] = None):
        """用 [start, current) 这段源码构造 Token 并加入列表。

        lexeme 来自切片，literal 只对 NUMBER / TRUE / FALSE 有意义，
        其余传 None。行号用当前 self.line，所以跨行的 Token 会记在结束行。
        """
        text = self.source[self.start:self.current]
        self.tokens.append(Token(type_, text, literal, self.line))