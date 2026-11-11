"""Small dependency-free minifiers for the site's own CSS and JS.

The sources in css/ and js/ stay readable; build.py minifies them on the way
into docs/. Both functions are deliberately conservative: they strip comments
and redundant whitespace but never rename identifiers or reorder anything.
"""

import re

_WORD = re.compile(r"[A-Za-z0-9_$]")


def _scan_string(s, i):
    """Return the index just past the quoted string starting at s[i]."""
    quote = s[i]
    i += 1
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == quote:
            return i + 1
        i += 1
    return i


def minify_css(css):
    out = []
    i, n = 0, len(css)
    while i < n:
        c = css[i]
        if c in "\"'":
            j = _scan_string(css, i)
            out.append(css[i:j])
            i = j
        elif css.startswith("/*", i):
            end = css.find("*/", i + 2)
            i = n if end == -1 else end + 2
            out.append(" ")
        else:
            out.append(c)
            i += 1
    text = "".join(out)
    # Split on strings so whitespace rules never touch string contents.
    parts = re.split(r"(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')", text)
    for k in range(0, len(parts), 2):
        p = re.sub(r"\s+", " ", parts[k])
        p = re.sub(r" ?([{};,>]) ?", r"\1", p)
        p = re.sub(r": ", ":", p)
        p = p.replace(";}", "}")
        parts[k] = p
    return "".join(parts).strip() + "\n"


def minify_js(js):
    out = []  # (kind, text) where kind is "code", "str" or "nl"
    i, n = 0, len(js)
    last = ""  # last significant character emitted
    last_word = ""

    def regex_allowed():
        if last == "" or last in "(,=:[!&|?{};+-*%<>~^":
            return True
        return last_word in ("return", "typeof", "case", "in", "of", "delete", "void", "throw")

    while i < n:
        c = js[i]
        if c in "\"'`":
            j = _scan_string(js, i)
            out.append(("str", js[i:j]))
            last, last_word = c, ""
            i = j
        elif js.startswith("//", i):
            j = js.find("\n", i)
            i = n if j == -1 else j
        elif js.startswith("/*", i):
            end = js.find("*/", i + 2)
            j = n if end == -1 else end + 2
            out.append(("nl" if "\n" in js[i:j] else "ws", ""))
            i = j
        elif c == "/" and regex_allowed():
            j = i + 1
            in_class = False
            while j < n:
                if js[j] == "\\":
                    j += 2
                    continue
                if js[j] == "[":
                    in_class = True
                elif js[j] == "]":
                    in_class = False
                elif js[j] == "/" and not in_class:
                    j += 1
                    break
                j += 1
            while j < n and _WORD.match(js[j]):
                j += 1
            out.append(("str", js[i:j]))
            last, last_word = "/", ""
            i = j
        elif c in " \t\r\n":
            j = i
            while j < n and js[j] in " \t\r\n":
                j += 1
            out.append(("nl" if "\n" in js[i:j] else "ws", ""))
            i = j
        else:
            j = i
            if _WORD.match(c):
                while j < n and _WORD.match(js[j]):
                    j += 1
                last_word = js[i:j]
            else:
                j = i + 1
                last_word = ""
            out.append(("code", js[i:j]))
            last = js[j - 1]
            i = j

    # Rebuild: keep one newline per whitespace run that had one (safe for ASI),
    # otherwise one space only where dropping it would merge two tokens.
    res = []
    pending = None
    prev = ""
    for kind, text in out:
        if kind in ("ws", "nl"):
            if pending != "nl":
                pending = kind
            continue
        if pending == "nl":
            if res and res[-1] != "\n":
                res.append("\n")
        elif pending == "ws" and prev:
            first = text[0]
            if (_WORD.match(prev) and _WORD.match(first)) or (prev in "+-" and first == prev):
                res.append(" ")
        pending = None
        res.append(text)
        prev = text[-1]
    return "".join(res).strip() + "\n"
