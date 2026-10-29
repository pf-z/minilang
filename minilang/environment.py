"""
minilang 运行时作用域环境。

解释器用它在执行期记录"变量名 → 值"的绑定。
每个 Environment 是一层作用域，enclosing 指向父层，形成环境链。
查找和赋值都沿链向上，define 只写当前层。
"""

from typing import Any, Dict, Optional


class Environment:
    def __init__(self, enclosing: Optional["Environment"] = None):
        # 当前层的变量绑定。键是变量名，值是运行时值（int/bool/函数/nil）
        self.values: Dict[str, Any] = {}
        # 父环境。全局环境为 None；块、函数调用会新建一层并指向当前环境
        self.enclosing: Optional["Environment"] = enclosing

    def define(self, name: str, value: Any):
        """在当前层新增绑定。

        let 声明走这里。只写当前层，不查父层，
        所以内层 let x 会遮蔽外层 x，而不是覆盖它。
        """
        self.values[name] = value

    def get(self, name: str) -> Any:
        """查变量值。当前层没有就沿 enclosing 向上找。

        内层能看见外层变量，外层看不见内层，
        因为查找方向是从当前层往父层走，不是反过来。
        """
        if name in self.values:
            return self.values[name]
        if self.enclosing is not None:
            return self.enclosing.get(name)
        # 找到全局环境还没有，说明变量从未声明
        raise RuntimeError(f"未定义变量: {name}")

    def assign(self, name: str, value: Any):
        """修改已存在的绑定。当前层没有就沿 enclosing 向上找。

        和 define 的区别：不会在当前层新建变量。
        找到哪个就改哪个，所以内层 x = 2 改的是外层那个 x（如果当前层没有 x），
        而不是新建一个遮蔽它。找不到才报错。
        """
        if name in self.values:
            self.values[name] = value
            return
        if self.enclosing is not None:
            self.enclosing.assign(name, value)
            return
        raise RuntimeError(f"赋值给未定义变量: {name}")