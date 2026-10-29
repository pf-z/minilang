中文 | [English](README.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.7+](https://img.shields.io/badge/Python-3.7%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-unittest-green.svg)](tests/)
[![Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#)

# minilang

一个极小语言实现，包含词法分析、递归下降语法分析、AST 打印、树遍历解释器、REPL 和测试。零第三方依赖，Python 3.7+ 即可运行。

## 语言特性

- 整数、布尔字面量
- 变量声明与赋值（`let x = 1;`）
- 算术、比较、逻辑运算（带优先级）
- `if / else`、`while`
- 函数定义与调用（支持递归和闭包）
- 块级作用域
- `return`
- 内置函数 `print`
- `//` 行注释

## 运行

```bash
# 运行示例
python main.py examples/fib.mini

# 打印 AST（不执行）
python main.py examples/fib.mini --ast

# 进入 REPL
python main.py

# 运行测试
python -m unittest discover -s tests -v
```

也支持 `python -m minilang`，行为与 `python main.py` 一致。

**REPL 注意事项**：逐行读取，每条语句必须写在一行内。多行结构（如跨行的 `if` 块）请写成 `.mini` 文件后执行。

## 项目结构

```
minilang/
├── README.md
├── docs/
│   └── grammar.ebnf          # 权威文法规格
├── main.py                   # 入口，调用 mini_lang.main
├── examples/
│   ├── fib.mini              # 递归与 while 示例
│   └── closure.mini          # 闭包示例
├── minilang/
│   ├── __init__.py
│   ├── __main__.py           # 支持 python -m mini_lang
│   ├── tokens.py             # Token 类型与关键字表
│   ├── lexer.py              # 词法分析器
│   ├── ast_nodes.py          # AST 节点（dataclass）
│   ├── parser.py             # 递归下降解析器
│   ├── ast_printer.py        # AST 调试打印器（--ast 用）
│   ├── environment.py        # 链式作用域环境
│   ├── interpreter.py        # 树遍历解释器
│   └── main.py               # 命令行入口与 REPL
└── tests/
    ├── test_mini.py          # 词法 / 解释器功能测试
    └── test_grammar.py       # 逐条文法规则的合法 / 非法用例
```

## 语法参考（EBNF）

权威版本见 `docs/grammar.ebnf`。下面这份与之一致，方便快速查阅。

```ebnf
program     → declaration* EOF

declaration → funDecl
            | varDecl
            | statement

funDecl     → "fun" IDENT "(" params? ")" block
varDecl     → "let" IDENT ("=" expression)? ";"

params      → IDENT ("," IDENT)*

statement   → exprStmt
            | ifStmt
            | whileStmt
            | returnStmt
            | block

exprStmt    → expression ";"
ifStmt      → "if" "(" expression ")" statement ("else" statement)?
whileStmt   → "while" "(" expression ")" statement
returnStmt  → "return" expression? ";"
block       → "{" declaration* "}"

expression  → assignment

assignment  → IDENT "=" assignment
            | equality

equality    → comparison (("==" | "!=") comparison)*
comparison  → term (("<" | ">") term)*
term        → factor (("+" | "-") factor)*
factor      → unary (("*" | "/") unary)*
unary       → ("!" | "-") unary
            | call
call        → primary ("(" arguments? ")")*
arguments   → expression ("," expression)*

primary     → NUMBER
            | "true"
            | "false"
            | IDENT
            | "(" expression ")"
```

### 文法符号说明

| 符号 | 含义 |
|---|---|
| `→` | 定义为 |
| `*` | 重复 0 次或多次 |
| `?` | 可选，出现 0 或 1 次 |
| `\|` | 二选一 |
| `"..."` | 字面量终结符 |

### 词法约定

- `NUMBER`：十进制整数字面量，如 `42`、`0`。
- `IDENT`：标识符，`[a-zA-Z_][a-zA-Z0-9_]*`，不能是关键字。
- 关键字：`let`、`fun`、`if`、`else`、`while`、`return`、`true`、`false`。
- 运算符与标点：`+ - * / ! < > == != = ; , ( ) { }`。
- `//` 到行尾为注释，词法阶段丢弃。
- `print` **不是关键字**，而是解释器启动时注入全局作用域的内置函数，因此可被用户变量遮蔽。

## 文法与解析器函数对应表

| 文法规则 | 解析器函数 | 关键实现 |
|---|---|---|
| `program` | `Parser.parse()` | 循环 `declaration()` 直到 EOF，错误时 `synchronize()` |
| `declaration` | `Parser.declaration()` | `FUN` → `fun_declaration`，`LET` → `var_declaration`，否则 `statement` |
| `funDecl` | `Parser.fun_declaration()` | 吃 `fun`、`IDENT`、`(`、参数、`)`、`block` |
| `varDecl` | `Parser.var_declaration()` | 吃 `let`、`IDENT`，可选 `=` + 表达式，吃 `;` |
| `params` | `Parser.fun_declaration()` 内循环 | `IDENT ("," IDENT)*` |
| `statement` | `Parser.statement()` | 按 Token 分派到 `if` / `while` / `return` / `block` / 表达式语句 |
| `block` | `Parser.block()` | 吃 `{`，循环 `declaration()` 直到 `}` |
| `ifStmt` | `Parser.if_statement()` | 可选 `else` 分支 |
| `whileStmt` | `Parser.while_statement()` | 循环体是单条 `statement` |
| `returnStmt` | `Parser.return_statement()` | 表达式可选 |
| `expression` | `Parser.expression()` | 直接转 `assignment()` |
| `assignment` | `Parser.assignment()` | 递归实现右结合；左侧必须是 `Var` |
| `equality` | `Parser.equality()` | `while` 循环实现左结合 |
| `comparison` | `Parser.comparison()` | 同上 |
| `term` | `Parser.term()` | 同上 |
| `factor` | `Parser.factor()` | 同上 |
| `unary` | `Parser.unary()` | 递归处理 `!` / `-` |
| `call` | `Parser.call()` | `while` 循环支持连续调用 `f(1)(2)` |
| `primary` | `Parser.primary()` | 字面量 / 变量 / 括号表达式 |

## 语义要点

- **作用域**：`let` 和 `fun` 在所在块内声明，块退出后不可见。函数体是新作用域，参数绑定在其中。
- **闭包**：函数对象保存定义时的环境引用，调用时以该环境为父环境新建作用域，因此能访问定义处的变量。
- **递归**：函数名在定义时绑定到当前环境，函数体内可引用自身。
- **`return`**：用 `ReturnSignal` 异常实现；在函数外出现 `return` 会转为运行时错误。
- **真值判断**：只有 `false` 和 `nil`（无返回值）为假，其余（包括 `0`）为真。
- **类型**：整数运算要求操作数严格为 `int`（`bool` 不参与算术）；`==` / `!=` 可比较任意值。
- **除法**：整数除法，向负无穷取整；除数为 `0` 时报运行时错误。
- **`print`**：接受一个参数，输出后换行；输出 `nil` 表示无返回值。

## 示例

### 递归与循环：`examples/fib.mini`

```
fun fib(n) {
  if (n < 2) { return n; }
  return fib(n - 1) + fib(n - 2);
}

let i = 0;
while (i < 10) {
  print(fib(i));
  i = i + 1;
}
```

输出：

```
0
1
1
2
3
5
8
13
21
34
```

### 闭包：`examples/closure.mini`

```
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
```

输出：

```
1
2
3
```

## 错误处理与退出码

- **词法错误**：非法字符按行号收集，全部报告后不再进入解析。
- **语法错误**：解析器在语句边界 `synchronize()`，一次运行可报告多个错误。
- **运行时错误**：未定义变量、赋值给未定义变量、除零、调用非函数、参数个数不匹配、函数外 `return` 等，均以 `运行时错误: ...` 输出到 stderr。
- **退出码**：成功为 `0`；任一阶段出错或文件读取失败为 `1`。REPL 不设置退出码，Ctrl-D 视为正常结束。

## 测试

```bash
python -m unittest discover -s tests -v
```

- `tests/test_mini.py`：功能级测试。词法覆盖最长匹配、关键字、注释；解释器覆盖算术、变量、控制流、递归、闭包、块作用域、运行时错误。
- `tests/test_grammar.py`：文法级测试。按 EBNF 产生式组织，每条规则至少一个合法用例和一个非法用例，保证文法与解析器同步。

两者分工：`test_mini.py` 问"这个功能对不对"，`test_grammar.py` 问"这条文法规则有没有被正确实现"。

## 设计约定

- 文法只描述语法结构；词法约定（关键字、标识符规则、注释）在 `tokens.py` 与 `lexer.py` 中实现。
- `print` 通过全局作用域注入而非关键字，使文法更统一，代价是它可被用户变量遮蔽。
- EBNF 是设计期规格与测试期依据，不参与运行时；解析器是手写递归下降，文法结构已硬编码在函数调用关系中。
- 新增语言特性时，顺序固定为：先改 `docs/grammar.ebnf`，再补 `tests/test_grammar.py`，最后改 `parser.py` 和 `interpreter.py`。
