"""The settings window's search: what comes first, what is left out."""
from hypr_screens.gui.search import Entry, match, normalize, rank


def entries():
    out = [
        Entry("Widgets", ["Appearance"], "widgets", "page", words="desktop, clock, lyrics"),
        Entry("Windows", ["Appearance"], "window", "page", words="gaps, blur"),
        Entry("Sound", ["Devices"], "sound", "page", words="volume, speaker"),
        Entry("Arrange on the desktop", ["Appearance", "Widgets"], "widgets", "row"),
        Entry("Blur", ["Appearance", "Windows"], "window", "group"),
        Entry("Blur strength", ["Appearance", "Windows"], "window", "row"),
    ]
    for kind, title in (("clock", "Clock"), ("lyrics", "Lyrics"), ("system", "System")):
        path = ["Appearance", "Widgets", title]
        out.append(Entry(title, ["Appearance", "Widgets"], f"widget-{kind}", "page",
                         parent_dest="widgets", parent_path=["Appearance", "Widgets"],
                         chain=["widgets", f"widget-{kind}"]))
        out.append(Entry(title, ["Appearance", "Widgets"], "widgets", "row", chain=["widgets"]))
        out.append(Entry("Colors", path, f"widget-{kind}-colors", "page", parent_dest=f"widget-{kind}",
                         parent_path=path, chain=["widgets", f"widget-{kind}", f"widget-{kind}-colors"]))
        out.append(Entry("Show this widget", path, f"widget-{kind}", "row",
                         parent_dest="widgets", parent_path=["Appearance", "Widgets"],
                         chain=["widgets", f"widget-{kind}"]))
        out.append(Entry("Accent color", path, f"widget-{kind}", "row",
                         parent_dest="widgets", parent_path=["Appearance", "Widgets"],
                         chain=["widgets", f"widget-{kind}"]))
    out.append(Entry("Größe und Platz", ["Appearance", "Widgets", "Clock"], "widget-clock", "row"))
    return out


def test_a_page_beats_the_rows_that_mention_it():
    results = rank(entries(), "widget")
    assert [(r.title, r.path) for r in results] == [("Widgets", ["Appearance"])]


def test_the_same_row_on_many_pages_comes_once():
    results = rank(entries(), "accent")
    assert [(r.title, r.dest, r.path) for r in results] == [("Accent color", "widgets", ["Appearance", "Widgets", "…"])]
    assert [(r.title, r.dest) for r in rank(entries(), "colors")] == [("Colors", "widgets")]


def test_a_page_hides_the_row_that_only_opens_it():
    assert [(r.title, r.dest) for r in rank(entries(), "clock")] == [("Clock", "widget-clock")]


def test_extra_words_find_a_page():
    assert [r.dest for r in rank(entries(), "volume")] == ["sound"]


def test_groups_and_rows_and_accents():
    assert [r.title for r in rank(entries(), "blur")][0] == "Blur"
    assert [r.title for r in rank(entries(), "grosse")] == ["Größe und Platz"]
    assert normalize("Größe") == "grosse"
    assert match("Blur strength", "str bl") > 0 and match("Blur", "sound") == 0
    assert rank(entries(), "   ") == [] and rank(entries(), "zzz") == []
