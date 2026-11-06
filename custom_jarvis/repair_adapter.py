"""A bounded Python-shaped argument adapter language, NOT arbitrary Python exec.

Only JSON data, assignments, conditions, returns and a small set of pure operations
are interpreted. No imports, filesystem, network, attributes outside whitelisted
method calls, loops, comprehensions, dynamic evaluation or host-object access.
"""

from __future__ import annotations

import ast
import json
import math
import operator
from typing import Any

MAX_BYTES = 65536
MAX_NUMBER = 10**12


class AdapterError(ValueError):
    pass


def encode_bounded(value: Any) -> str:
    try:
        encoded = json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise AdapterError("Adapter data must be finite, acyclic JSON") from exc
    if len(encoded.encode()) > MAX_BYTES:
        raise AdapterError("Adapter data exceeds 64 KB")
    return encoded


def bounded(value: Any) -> Any:
    encode_bounded(value)
    return value


class _Returned(Exception):
    def __init__(self, value):
        self.value = value


class AdapterProgram:
    METHODS = frozenset(
        {
            "get",
            "copy",
            "pop",
            "strip",
            "lower",
            "upper",
            "replace",
            "lstrip",
            "rstrip",
            "startswith",
            "endswith",
            "split",
            "join",
            "removeprefix",
            "removesuffix",
            "isdigit",
            "isdecimal",
            "keys",
            "values",
            "items",
            "setdefault",
        }
    )
    BUILTINS = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "len": len,
        "min": min,
        "max": max,
        "abs": abs,
        "dict": dict,
    }
    OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
    }
    COMPARISONS = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
    }
    ALLOWED = (
        ast.Module,
        ast.FunctionDef,
        ast.arguments,
        ast.arg,
        ast.Assign,
        ast.If,
        ast.Return,
        ast.Name,
        ast.Load,
        ast.Store,
        ast.Constant,
        ast.Dict,
        ast.List,
        ast.Tuple,
        ast.Subscript,
        ast.Call,
        ast.Attribute,
        ast.keyword,
        ast.BinOp,
        ast.UnaryOp,
        ast.BoolOp,
        ast.Compare,
        ast.IfExp,
        ast.And,
        ast.Or,
        ast.Not,
        ast.USub,
        ast.UAdd,
        ast.Add,
        ast.Sub,
        ast.Div,
        ast.FloorDiv,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.In,
        ast.NotIn,
    )

    def __init__(self, source: str):
        if len(source.encode()) > 8192:
            raise AdapterError("Adapter source exceeds 8 KB")
        try:
            module = ast.parse(source)
        except (SyntaxError, RecursionError) as exc:
            raise AdapterError(str(exc)) from exc
        nodes = list(ast.walk(module))
        if len(nodes) > 256:
            raise AdapterError("Adapter exceeds 256 AST nodes")
        if len(module.body) != 1 or not isinstance(module.body[0], ast.FunctionDef):
            raise AdapterError("Provide only def adapt(args)")
        function = module.body[0]
        arguments = function.args
        if (
            function.name != "adapt"
            or function.decorator_list
            or function.returns
            or len(arguments.args) != 1
            or arguments.args[0].arg != "args"
            or arguments.args[0].annotation
            or arguments.defaults
            or arguments.posonlyargs
            or arguments.kwonlyargs
            or arguments.kwarg
            or arguments.vararg
            or getattr(function, "type_params", [])
        ):
            raise AdapterError("Function must have signature def adapt(args)")
        for node in nodes:
            if not isinstance(node, self.ALLOWED):
                raise AdapterError(f"Unsupported adapter syntax: {type(node).__name__}")
            if isinstance(node, ast.Name) and ("__" in node.id or len(node.id) > 40):
                raise AdapterError("Invalid adapter name")
            if isinstance(node, ast.Attribute) and node.attr not in self.METHODS:
                raise AdapterError(f"Method not allowed: {node.attr}")
            if isinstance(node, ast.Assign):
                if len(node.targets) != 1 or not isinstance(
                    node.targets[0], (ast.Name, ast.Subscript)
                ):
                    raise AdapterError("Use single-name or dictionary-item assignments")
                if isinstance(node.targets[0], ast.Name) and node.targets[
                    0
                ].id in self.BUILTINS | {"args": None}:
                    raise AdapterError("Cannot overwrite reserved adapter names")
        self.body = function.body

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            raise AdapterError("Adapter input must be a dictionary")
        # JSON copying prevents mutations to the caller and excludes host objects.
        environment = {"args": json.loads(encode_bounded(arguments))}
        budget = [1024]
        try:
            self._statements(self.body, environment, budget)
        except _Returned as returned:
            result = bounded(returned.value)
            if not isinstance(result, dict) or any(
                not isinstance(k, str) for k in result
            ):
                raise AdapterError("Adapter must return a dictionary with string keys")
            return result
        except AdapterError:
            raise
        except (
            LookupError,
            TypeError,
            ValueError,
            OverflowError,
            ZeroDivisionError,
        ) as exc:
            raise AdapterError(f"Adapter runtime error: {exc}") from exc
        raise AdapterError("Adapter did not return a value")

    @staticmethod
    def _tick(budget):
        budget[0] -= 1
        if budget[0] < 0:
            raise AdapterError("Adapter operation budget exhausted")

    def _statements(self, statements, env, budget):
        for statement in statements:
            self._tick(budget)
            if isinstance(statement, ast.Return):
                raise _Returned(self._eval(statement.value, env, budget))
            if isinstance(statement, ast.If):
                selected = (
                    statement.body
                    if self._eval(statement.test, env, budget)
                    else statement.orelse
                )
                self._statements(selected, env, budget)
            elif isinstance(statement, ast.Assign):
                value = bounded(self._eval(statement.value, env, budget))
                target = statement.targets[0]
                if isinstance(target, ast.Name):
                    env[target.id] = value
                else:
                    container = self._eval(target.value, env, budget)
                    key = self._eval(target.slice, env, budget)
                    if not isinstance(container, dict) or not isinstance(key, str):
                        raise AdapterError("Only dictionary items can be assigned")
                    container[key] = value
                    bounded(container)
            else:
                raise AdapterError("Unsupported statement position")

    def _eval(self, node, env, budget):
        self._tick(budget)
        if isinstance(node, ast.Constant):
            return self._checked(node.value)
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise AdapterError(f"Unknown value name: {node.id}")
            return env[node.id]
        if isinstance(node, ast.Dict):
            if any(key is None for key in node.keys):
                raise AdapterError("Dictionary unpacking is not supported")
            return bounded(
                {
                    self._eval(k, env, budget): self._eval(v, env, budget)
                    for k, v in zip(node.keys, node.values)
                }
            )
        if isinstance(node, (ast.List, ast.Tuple)):
            return bounded([self._eval(item, env, budget) for item in node.elts])
        if isinstance(node, ast.Subscript):
            return self._eval(node.value, env, budget)[
                self._eval(node.slice, env, budget)
            ]
        if isinstance(node, ast.IfExp):
            return self._eval(
                node.body if self._eval(node.test, env, budget) else node.orelse,
                env,
                budget,
            )
        if isinstance(node, ast.UnaryOp):
            value = self._eval(node.operand, env, budget)
            if isinstance(node.op, ast.Not):
                return not value
            if not isinstance(value, (int, float)):
                raise AdapterError("Numeric unary operation required")
            return self._checked(-value if isinstance(node.op, ast.USub) else +value)
        if isinstance(node, ast.BinOp):
            left, right = (
                self._eval(node.left, env, budget),
                self._eval(node.right, env, budget),
            )
            if not (
                isinstance(left, (str, int, float))
                and isinstance(right, (str, int, float))
            ):
                raise AdapterError("Binary operators accept only scalar values")
            return self._checked(self.OPERATORS[type(node.op)](left, right))
        if isinstance(node, ast.BoolOp):
            value = None
            for item in node.values:
                value = self._eval(item, env, budget)
                if (isinstance(node.op, ast.And) and not value) or (
                    isinstance(node.op, ast.Or) and value
                ):
                    break
            return value
        if isinstance(node, ast.Compare):
            left = self._eval(node.left, env, budget)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator, env, budget)
                if not self.COMPARISONS[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            return self._call(node, env, budget)
        raise AdapterError(f"Unsupported expression: {type(node).__name__}")

    @staticmethod
    def _checked(value):
        if isinstance(value, (int, float)) and (
            not math.isfinite(value) or abs(value) > MAX_NUMBER
        ):
            raise AdapterError("Adapter numeric value exceeds finite range")
        return bounded(value)

    def _call(self, node, env, budget):
        args = [self._eval(item, env, budget) for item in node.args]
        if any(item.arg is None for item in node.keywords):
            raise AdapterError("Keyword unpacking is not supported")
        kwargs = {
            item.arg: self._eval(item.value, env, budget) for item in node.keywords
        }
        if isinstance(node.func, ast.Name) and node.func.id in self.BUILTINS:
            if kwargs and node.func.id != "dict":
                raise AdapterError("Only dict() accepts keyword arguments")
            return self._checked(self.BUILTINS[node.func.id](*args, **kwargs))
        if not isinstance(node.func, ast.Attribute) or kwargs:
            raise AdapterError("Only approved pure calls are allowed")
        owner = self._eval(node.func.value, env, budget)
        method = node.func.attr
        if isinstance(owner, dict) and method in (
            "get",
            "copy",
            "pop",
            "keys",
            "values",
            "items",
            "setdefault",
        ):
            if method in ("keys", "values", "items"):
                return bounded(list(getattr(owner, method)(*args)))
            return bounded(getattr(owner, method)(*args))
        if isinstance(owner, str) and method in (
            "strip",
            "lower",
            "upper",
            "replace",
            "lstrip",
            "rstrip",
            "startswith",
            "endswith",
            "split",
            "join",
            "removeprefix",
            "removesuffix",
            "isdigit",
            "isdecimal",
        ):
            if method == "join":
                if (
                    len(args) != 1
                    or not isinstance(args[0], (list, tuple))
                    or not all(isinstance(x, str) for x in args[0])
                ):
                    raise AdapterError("join requires a bounded string list")
                size = sum(len(x.encode()) for x in args[0]) + max(
                    0, len(args[0]) - 1
                ) * len(owner.encode())
                if size > MAX_BYTES:
                    raise AdapterError("join expansion exceeds size limit")
            if method == "replace":
                if len(args) not in (2, 3) or not all(
                    isinstance(x, str) for x in args[:2]
                ):
                    raise AdapterError("replace() needs string arguments")
                count = owner.count(args[0])
                if len(args) == 3:
                    if not isinstance(args[2], int):
                        raise AdapterError("replace count must be an integer")
                    count = min(count, args[2]) if args[2] >= 0 else count
                if len(owner) + count * max(0, len(args[1]) - len(args[0])) > MAX_BYTES:
                    raise AdapterError("replace() expansion exceeds size limit")
            return self._checked(getattr(owner, method)(*args))
        raise AdapterError("Method is not available on this JSON value")
