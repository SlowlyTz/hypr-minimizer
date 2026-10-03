"""Every text the settings window passes through i18n.t(), found in the code."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "hypr_screens"


def literal_keys() -> set[str]:
    """First arguments of t("...") calls that are plain strings."""
    keys = set()
    for path in ROOT.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(), str(path))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t"
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                keys.add(node.args[0].value)
    return keys


def table_keys() -> set[str]:
    """Texts kept in tables and translated through t(variable)."""
    from hypr_screens import samsung, sound
    from hypr_screens.gui import texts

    keys = {title for _key, title, _icon in texts.PAGE_LIST}
    for title, explanation in texts.SETTINGS.values():
        keys |= {title, explanation}
    keys |= set(texts.ACTION_HELP.values()) | set(texts.ACTION_LABELS.values())
    for title, text in texts.HELP:
        keys |= {title, text}
    keys |= set(sound.PORT_LABELS.values())
    keys |= {label for _mode, label, _cpu in samsung.MODES} | set(samsung.ATTRIBUTES.values())
    keys |= set(texts.MODE_HINTS.values()) | set(texts.BATTERY_ROWS.values())
    keys |= personalization_keys() | widgets_keys()
    return keys


def personalization_keys() -> set[str]:
    """The page's tables, read without importing GTK."""
    from hypr_screens import look

    source = (ROOT / "gui" / "personalization_page.py").read_text()
    tree = ast.parse(source)
    keys = set(look.PRESETS)
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets[0].id == "CARDS":
            keys |= {text for _page, title, caption, _icon in ast.literal_eval(node.value) for text in (title, caption)}
        if isinstance(node, ast.Assign) and node.targets[0].id in ("SLIDERS", "GROUPS"):
            value = ast.literal_eval(node.value)
            if isinstance(value, dict):
                for title, subtitle, _percent in value.values():
                    keys |= {text for text in (title, subtitle) if text}
            else:
                keys |= {title for title, _keys in value}
    return keys


def widgets_keys() -> set[str]:
    from hypr_screens import widgets

    source = (ROOT / "gui" / "widgets_tab.py").read_text()
    keys = set(widgets.TITLES.values())
    for group, parts in [*(g for groups in widgets.PARTS.values() for g in groups), widgets.LOOK_PARTS]:
        keys |= {group} | {title for _part, title, _default in parts}
    colors = (ROOT / "gui" / "widget_colors.py").read_text()
    for node in ast.parse(colors).body:
        if isinstance(node, ast.Assign) and node.targets[0].id == "THEME_NAMES":
            keys |= set(ast.literal_eval(node.value).values())
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign):
            continue
        name = node.targets[0].id
        if name in ("CHOICE_TITLES", "SWITCH_TITLES", "DESCRIPTIONS", "HINTS"):
            keys |= set(ast.literal_eval(node.value).values())
        if name == "CHOICE_LABELS":
            keys |= {text for labels in ast.literal_eval(node.value).values() for text in labels.values()}
        if name == "SECTIONS":
            keys |= {item.elts[0].value for item in ast.walk(node.value)
                     if isinstance(item, ast.Tuple) and item.elts and isinstance(item.elts[0], ast.Constant)}
        if name == "EXPANDERS":
            keys |= {title for title, _keys in ast.literal_eval(node.value).values()}
        if name == "NUMBER_ROWS":
            keys |= set(ast.literal_eval(node.value).values())
        if name == "SLIDER_ROWS":
            keys |= {title for title, _step, _unit in ast.literal_eval(node.value).values()}
    return keys


def all_keys() -> set[str]:
    return literal_keys() | table_keys()
