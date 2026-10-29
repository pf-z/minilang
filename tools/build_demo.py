"""
生成可视化演示数据。

用法：
    python tools/build_demo.py

对 examples/ 下每个 .mini 文件跑 lexer/parser/interpreter，
收集 Token、AST、执行轨迹，写到 docs/demo/data/<name>.json。

不改 minilang/ 下任何代码。位置信息由 inject_position_tracking
在运行时给 Parser 实例打补丁获得，执行轨迹由 RecordingInterpreter
子类覆写获得。

JSON 契约：
{
  "name": str,
  "source": str,
  "tokens": [{"id": int, "type": str, "lexeme": str, "literal": any,
              "line": int, "start": int, "end": int}],
  "ast": [{"id": int, "type": str, "label": str,
           "tokenStart": int, "tokenEnd": int,
           "ownTokens": [int], "allTokens": [int],
           "fields": [[str, str], ...],
           "children": [...]}],
  "execution": [{"step": int, "nodeId": int|null,
                 "action": "execute"|"evaluate"|"print"|"error",
                 "phase": "enter"|"exit"|"output",
                 "env": [{"depth": int, "values": {str: str}}],
                 "output": str|null}],
  "errors": [str]
}

ownTokens：节点直接拥有、不属于任何子节点的 Token 下标。
allTokens：节点自身和所有子节点的 Token 下标并集，等于 tokenStart..tokenEnd。
fields：节点在语言定义里的字段名和值。值是子节点时显示子节点类型，
        是列表时显示元素类型列表，是标量时显示 repr。
"""

import dataclasses
import functools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from minilang.lexer import Lexer
from minilang.parser import Parser
from minilang.interpreter import Interpreter, MiniCallable
from minilang import ast_nodes as ast


# ---------- 位置追踪：运行时给 Parser 实例打补丁 ----------

def inject_position_tracking(parser):
    """给 parser 实例的所有公开方法包一层，记录 AST 节点的 Token 范围。

    - 关键字节点（ReturnStmt/IfStmt/WhileStmt/FunctionDecl/VarDecl）：
      tokenStart 回退到父方法进入时的 current，把关键字包含进来。
    - Block：block() 进入时左花括号已被父方法吃掉，tokenStart 回退一位
      到 { 的下标。
    - 其他节点：tokenStart 用自己的 own_start。
    """
    KEYWORD_NODES = {"ReturnStmt", "IfStmt", "WhileStmt", "FunctionDecl", "VarDecl"}
    positions = {}
    start_stack = []

    names = [
        n for n in dir(parser)
        if not n.startswith("_")
        and n != "parse"
        and callable(getattr(parser, n))
    ]

    for name in names:
        original = getattr(parser, name)

        @functools.wraps(original)
        def wrapper(*args, __original=original, **kwargs):
            own_start = parser.current
            start_stack.append(own_start)
            try:
                node = __original(*args, **kwargs)
            finally:
                start_stack.pop()
            end = parser.current - 1
            if isinstance(node, (ast.Expr, ast.Stmt)) and id(node) not in positions:
                type_name = type(node).__name__
                if type_name == "Block" and own_start > 0:
                    node_start = own_start - 1
                elif type_name in KEYWORD_NODES and start_stack:
                    node_start = start_stack[-1]
                else:
                    node_start = own_start
                positions[id(node)] = (node_start, end)
            return node

        setattr(parser, name, wrapper)

    return positions


# ---------- AST 标签 ----------

def build_label(node):
    """生成节点展示文本。默认规则自动适配新类型，特殊类型可加分支。"""
    t = type(node).__name__

    if t == "Literal":
        return f"Literal {node.value}"
    if t == "Var":
        return f"Var {node.name}"
    if t == "Assign":
        return f"Assign {node.name}"
    if t == "Unary":
        return f"Unary {node.op}"
    if t == "Binary":
        return f"Binary {node.op}"
    if t == "Call":
        return "Call"
    if t == "ExprStmt":
        return "ExprStmt"
    if t == "VarDecl":
        return f"let {node.name}"
    if t == "Block":
        return "Block"
    if t == "IfStmt":
        return "if"
    if t == "WhileStmt":
        return "while"
    if t == "FunctionDecl":
        return f"fun {node.name}({', '.join(node.params)})"
    if t == "ReturnStmt":
        return "return"

    parts = [t]
    for field_name in ("op", "name", "value", "params"):
        if hasattr(node, field_name):
            v = getattr(node, field_name)
            if v is not None and v != []:
                parts.append(str(v))
    return " ".join(parts)


# ---------- AST 字段 ----------

def serialize_fields(node):
    """输出节点在语言定义里的字段名和值。

    值是子节点时显示子节点类型，是列表时显示元素类型列表，
    是标量时显示 repr。这样右侧面板展示的是 ast_nodes.py 里的真实定义，
    而不是实现细节。
    """
    fields = []
    for f in dataclasses.fields(node):
        value = getattr(node, f.name)
        if isinstance(value, (ast.Expr, ast.Stmt)):
            fields.append([f.name, type(value).__name__])
        elif isinstance(value, list):
            if not value:
                fields.append([f.name, "[]"])
            elif all(isinstance(x, (ast.Expr, ast.Stmt)) for x in value):
                fields.append([f.name, "[" + ", ".join(type(x).__name__ for x in value) + "]"])
            else:
                fields.append([f.name, repr(value)])
        else:
            fields.append([f.name, repr(value)])
    return fields


# ---------- AST 序列化 ----------

def serialize_node(node, recorder):
    children = []
    for f in dataclasses.fields(node):
        value = getattr(node, f.name)
        if isinstance(value, (ast.Expr, ast.Stmt)):
            children.append(serialize_node(value, recorder))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, (ast.Expr, ast.Stmt)):
                    children.append(serialize_node(item, recorder))

    start, end = recorder.positions.get(id(node), (-1, -1))

    if start < 0:
        own = []
        all_tokens = []
    else:
        covered = set()
        for c in children:
            covered.update(c["allTokens"])
        own = [t for t in range(start, end + 1) if t not in covered]
        all_set = set(own)
        for c in children:
            all_set.update(c["allTokens"])
        all_tokens = sorted(all_set)

    return {
        "id": recorder.node_id(node),
        "type": type(node).__name__,
        "label": build_label(node),
        "tokenStart": start,
        "tokenEnd": end,
        "ownTokens": own,
        "allTokens": all_tokens,
        "fields": serialize_fields(node),
        "children": children,
    }


def serialize_ast(statements, recorder):
    return [serialize_node(s, recorder) for s in statements]


# ---------- 执行记录 ----------

class ExecutionRecorder:
    """收集执行轨迹，并给每个 AST 节点分配稳定的整数 ID。"""

    def __init__(self, positions):
        self.events = []
        self._node_ids = {}
        self._next_id = 1
        self.positions = positions

    def node_id(self, node):
        key = id(node)
        if key not in self._node_ids:
            self._node_ids[key] = self._next_id
            self._next_id += 1
        return self._node_ids[key]

    def snapshot_env(self, env):
        chain = []
        current = env
        while current is not None:
            chain.append(current)
            current = current.enclosing
        result = []
        for depth, layer in enumerate(reversed(chain)):
            entries = {}
            for name, value in layer.values.items():
                entries[name] = self.stringify(value)
            result.append({"depth": len(chain) - depth - 1, "values": entries})
        return result

    @staticmethod
    def stringify(value):
        if value is None:
            return "nil"
        if value is True:
            return "true"
        if value is False:
            return "false"
        if isinstance(value, (int, str)):
            return str(value)
        return repr(value)

    def on_execute_enter(self, stmt, env):
        self._record(stmt, "execute", "enter", env)

    def on_execute_exit(self, stmt, env):
        self._record(stmt, "execute", "exit", env)

    def on_evaluate_enter(self, expr, env):
        self._record(expr, "evaluate", "enter", env)

    def on_evaluate_exit(self, expr, env):
        self._record(expr, "evaluate", "exit", env)

    def _record(self, node, action, phase, env):
        self.events.append({
            "step": len(self.events),
            "nodeId": self.node_id(node),
            "action": action,
            "phase": phase,
            "env": self.snapshot_env(env),
            "output": None,
        })

    def record_print(self, text):
        self.events.append({
            "step": len(self.events),
            "nodeId": None,
            "action": "print",
            "phase": "output",
            "env": [],
            "output": text,
        })

    def record_error(self, text):
        self.events.append({
            "step": len(self.events),
            "nodeId": None,
            "action": "error",
            "phase": "output",
            "env": [],
            "output": text,
        })


class RecordingInterpreter(Interpreter):
    """子类覆写 execute/evaluate 记录事件，不改父类任何代码。"""

    def __init__(self, recorder):
        super().__init__()
        self.recorder = recorder

    def execute(self, stmt):
        self.recorder.on_execute_enter(stmt, self.environment)
        try:
            super().execute(stmt)
        finally:
            self.recorder.on_execute_exit(stmt, self.environment)

    def evaluate(self, expr):
        self.recorder.on_evaluate_enter(expr, self.environment)
        try:
            return super().evaluate(expr)
        finally:
            self.recorder.on_evaluate_exit(expr, self.environment)


class RecordingPrint(MiniCallable):
    """替换内置 print，记录输出并返回 nil。

    继承 MiniCallable 是为了通过 evaluate 的 Call 分支的 isinstance 检查。
    """

    def __init__(self, recorder):
        self.recorder = recorder

    def arity(self) -> int:
        return 1

    def call(self, interpreter, arguments):
        text = interpreter.stringify(arguments[0])
        self.recorder.record_print(text)
        return None

    def __repr__(self):
        return "<记录用 print>"


# ---------- Token 字符区间 ----------

def collect_tokens(source, tokens):
    result = []
    cursor = 0
    for i, t in enumerate(tokens):
        if t.type.name == "EOF":
            start = end = len(source)
        else:
            while cursor < len(source) and source[cursor:cursor + len(t.lexeme)] != t.lexeme:
                cursor += 1
            start = cursor
            end = cursor + len(t.lexeme)
            cursor = end
        result.append({
            "id": i,
            "type": t.type.name,
            "lexeme": t.lexeme,
            "literal": t.literal,
            "line": t.line,
            "start": start,
            "end": end,
        })
    return result


# ---------- 收集 ----------

def collect(source):
    lexer = Lexer(source)
    tokens = lexer.scan_tokens()
    token_data = collect_tokens(source, tokens)

    parser = Parser(tokens)
    positions = inject_position_tracking(parser)
    statements, errors = parser.parse()

    if errors:
        return {
            "source": source,
            "tokens": token_data,
            "ast": [],
            "execution": [],
            "errors": errors,
        }

    recorder = ExecutionRecorder(positions)
    ast_data = serialize_ast(statements, recorder)

    interpreter = RecordingInterpreter(recorder)
    interpreter.globals.values["print"] = RecordingPrint(recorder)

    try:
        interpreter.interpret(statements)
    except RuntimeError as e:
        recorder.record_error(f"运行时错误: {e}")

    return {
        "source": source,
        "tokens": token_data,
        "ast": ast_data,
        "execution": recorder.events,
        "errors": [],
    }


def main():
    examples_dir = ROOT / "examples"
    out_dir = ROOT / "docs" / "demo" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    for mini in sorted(examples_dir.glob("*.mini")):
        print(f"处理 {mini.name}")
        source = mini.read_text(encoding="utf-8")
        data = collect(source)
        data["name"] = mini.stem
        out = out_dir / f"{mini.stem}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"  写入 {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()