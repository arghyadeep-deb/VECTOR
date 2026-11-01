"""Restricted AST evaluators for expression-only runtime features."""

from __future__ import annotations

import ast
import operator
from collections.abc import Mapping
from typing import Any


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}
_CMP_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


class UnsafeExpressionError(ValueError):
    """Raised when an expression uses syntax outside the safe subset."""


def safe_eval_expression(expression: str, names: Mapping[str, Any]) -> Any:
    """Evaluate a Python expression subset without ``eval``.

    The evaluator is intended for formulas over already-trusted objects such as
    pandas Series and whitelisted functions. It rejects imports, assignments,
    comprehensions, lambdas, dunder attribute access, and unknown names.
    """
    if not isinstance(expression, str) or not expression.strip():
        raise UnsafeExpressionError("expression must be a non-empty string")
    tree = ast.parse(expression, mode="eval")

    def _ev(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in names:
                return names[node.id]
            raise UnsafeExpressionError(f"name not allowed: {node.id}")
        if isinstance(node, ast.BinOp):
            fn = _BIN_OPS.get(type(node.op))
            if fn is None:
                raise UnsafeExpressionError(f"operator not allowed: {type(node.op).__name__}")
            return fn(_ev(node.left), _ev(node.right))
        if isinstance(node, ast.UnaryOp):
            fn = _UNARY_OPS.get(type(node.op))
            if fn is None:
                raise UnsafeExpressionError(f"operator not allowed: {type(node.op).__name__}")
            return fn(_ev(node.operand))
        if isinstance(node, ast.BoolOp):
            values = [_ev(v) for v in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare):
            left = _ev(node.left)
            for op, comp in zip(node.ops, node.comparators):
                fn = _CMP_OPS.get(type(op))
                if fn is None:
                    raise UnsafeExpressionError(f"comparison not allowed: {type(op).__name__}")
                right = _ev(comp)
                if not fn(left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return _ev(node.body) if _ev(node.test) else _ev(node.orelse)
        if isinstance(node, ast.Call):
            func = _ev(node.func)
            args = [_ev(arg) for arg in node.args]
            kwargs = {kw.arg: _ev(kw.value) for kw in node.keywords if kw.arg is not None}
            return func(*args, **kwargs)
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                raise UnsafeExpressionError("dunder attribute access is not allowed")
            return getattr(_ev(node.value), node.attr)
        if isinstance(node, ast.Subscript):
            return _ev(node.value)[_ev(node.slice)]
        if isinstance(node, ast.List):
            return [_ev(elt) for elt in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(_ev(elt) for elt in node.elts)
        if isinstance(node, ast.Dict):
            return {_ev(k): _ev(v) for k, v in zip(node.keys, node.values)}
        raise UnsafeExpressionError(f"syntax not allowed: {type(node).__name__}")

    return _ev(tree)
