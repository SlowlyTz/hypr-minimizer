"""Thin hyprctl wrappers. hypr-screens needs Hyprland >= 0.56 (Lua dispatchers)."""
import json
import subprocess


def hyprctl(*args: str) -> str:
    return subprocess.run(
        ["hyprctl", *args], check=False, text=True, capture_output=True
    ).stdout


def query(what: str, *args: str) -> object:
    try:
        return json.loads(hyprctl("-j", what, *args) or "null")
    except json.JSONDecodeError:
        return None


def query_list(what: str, *args: str) -> list[dict]:
    result = query(what, *args)
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, dict)]


def monitors(include_disabled: bool = False) -> list[dict]:
    return query_list("monitors", "all") if include_disabled else query_list("monitors")


def dispatch(expression: str) -> str:
    return hyprctl("dispatch", expression)


def eval_lua(code: str) -> str:
    return hyprctl("eval", code)


def lua_string(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'
