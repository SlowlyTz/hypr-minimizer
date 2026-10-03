"""The search of the settings window: what it finds and in which order.

The window collects entries from what it shows (gui/window.py): every page,
every group and every row, each with its place as a path of titles
("Appearance → Widgets → Clock"). rank() keeps the ones that fit the query
and orders them, so the best result comes first:

- a page whose title fits beats a group, a group beats a row, a row's own
  title beats its subtitle and a page's extra search words;
- results far below the best one are dropped – "widget" finds the Widgets
  page, not every row that mentions a widget;
- the same title on many pages under one place ("Accent color" on every
  widget, each widget's "Colors" page) comes once, leading to that place;
- a page in the results stands for the rows of its family (itself, the page
  above it and the pages under it) that only repeat its title – the row on
  the Widgets page that opens the clock is not shown next to the clock;
- one result per place.

No GTK here: an entry's `target` is whatever the window wants back.
"""
import unicodedata
from dataclasses import dataclass, field

MAX_RESULTS = 10
# Results below this share of the best score are left out.
KEEP_SHARE = 0.5
# How much an entry's kind counts, and a page's extra words.
WEIGHTS = {"page": 1.3, "group": 0.95, "row": 0.85, "subtitle": 0.45, "words": 0.75}
# Rows with the same title on at least this many pages become one result.
FOLD_AT = 3


@dataclass
class Entry:
    title: str
    path: list[str]            # the titles of the places above it, outermost first
    dest: str                  # the page it is on
    kind: str                  # "page", "group" or "row"
    subtitle: str = ""
    words: str = ""            # a page's extra search words
    target: object = None
    parent_dest: str = ""      # the page above `dest` (for folding)
    parent_path: list[str] = field(default_factory=list)
    chain: list[str] = field(default_factory=list)   # the keys from the top page down to `dest`


@dataclass
class Result:
    title: str
    path: list[str]
    dest: str
    target: object
    score: float


def normalize(text: str) -> str:
    """Lower case without accents: "Größe" finds "grosse" and the other way round."""
    text = str(text).lower().replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def match(text: str, query: str) -> float:
    """0 when not every word of the query is in the text; more the better it fits."""
    text, words = normalize(text), normalize(query).split()
    if not words or not text:
        return 0.0
    tokens = [token for token in "".join(c if c.isalnum() else " " for c in text).split()]
    total = 0.0
    for word in words:
        if any(token.startswith(word) for token in tokens):
            total += 1.0 if any(token == word for token in tokens) else 0.85
        elif word in text:
            # Inside a word: German puts words together ("Rahmenfarben").
            total += 0.7 if len(word) >= 4 else 0.4
        else:
            return 0.0
    score = total / len(words) * 100
    if text.startswith(normalize(query).strip()):
        score += 15
    return score


def score(entry: Entry, query: str) -> float:
    best = match(entry.title, query) * WEIGHTS[entry.kind]
    if entry.subtitle:
        best = max(best, match(entry.subtitle, query) * WEIGHTS["subtitle"])
    if entry.words:
        best = max(best, match(entry.words, query) * WEIGHTS["words"])
    return best


def rank(entries: list[Entry], query: str) -> list[Result]:
    if not query.strip():
        return []
    scored = [(score(entry, query), entry) for entry in entries]
    scored = [(s, e) for s, e in scored if s > 0]
    if not scored:
        return []
    scored.sort(key=lambda item: -item[0])
    top = scored[0][0]
    scored = [(s, e) for s, e in scored if s >= top * KEEP_SHARE]

    # The same title on many pages under one place: one result there. A row
    # folds into the page above its page; a page into the one above its parent.
    def fold_place(e: Entry) -> str:
        if e.kind != "page":
            return e.parent_dest
        return e.chain[-3] if len(e.chain) >= 3 else ""

    places: dict[tuple[str, str], set[str]] = {}
    fold_paths: dict[str, list[str]] = {}
    for _s, e in scored:
        place = fold_place(e)
        if place:
            places.setdefault((normalize(e.title), place), set()).add(e.dest)
            fold_paths[place] = e.parent_path if e.kind != "page" else e.path[:-1]
    results: list[Result] = []
    seen: set[tuple] = set()
    # A page that fits at least as well stands for what is on it.
    page_scores = {e.dest: s for s, e in scored if e.kind == "page"}
    families = [(normalize(e.title), e) for _s, e in scored if e.kind == "page"]
    found_chains: list[list[str]] = []
    for s, e in scored:
        place = fold_place(e)
        if len(places.get((normalize(e.title), place), ())) >= FOLD_AT:
            key = ("fold", normalize(e.title), place)
            if key in seen or page_scores.get(place, -1) >= s:
                continue
            seen.add(key)
            # "→ …": it is on more than one page under there.
            results.append(Result(e.title, [*fold_paths[place], "…"], place, None, s))
            continue
        if e.kind == "page":
            if any(r.dest == e.dest for r in results):
                continue  # something on it already fits better
            if not match(e.title, query) and any(e.dest in chain[:-1] for chain in found_chains):
                continue  # found only by its extra words, and a page under it is there
        else:
            if page_scores.get(e.dest, -1) >= s:
                continue
            title = normalize(e.title)
            if any(title == name and (page.dest in e.chain or e.dest == page.parent_dest) for name, page in families):
                continue  # only repeats a page found already
        key = (e.dest, normalize(e.title))
        if key in seen:
            continue
        seen.add(key)
        results.append(Result(e.title, e.path, e.dest, e.target, s))
        found_chains.append(e.chain or [e.dest])
        if len(results) >= MAX_RESULTS:
            break
    return results
