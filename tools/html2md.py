"""Convert a built page's <main> content to clean Markdown (stdlib only).

Used by build.py to publish a .md copy of each page for agents. It keeps
headings, paragraphs, lists, links, emphasis, FAQ questions and contact
definitions, and drops scripts, SVG, media, forms and decorative elements.
"""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

SKIP = {"script", "style", "svg", "iframe", "video", "picture", "img", "form", "button", "noscript", "source"}
VOID = {"br", "img", "source", "input", "meta", "link", "hr", "wbr"}
BLOCK = {"p", "div", "section", "article", "figure", "figcaption", "address", "blockquote", "dl", "dt", "dd", "details", "summary", "header", "footer", "nav"}


class _MD(HTMLParser):
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.out = []
        self.buf = []
        self.skip_tag = None
        self.skip_depth = 0
        self.lists = []  # stack of [kind, counter]
        self.heading = None
        self.link = None
        self.last_link = None
        self.link_used = False
        self.quote = False
        self.summary = False
        self.dt = False

    # helpers
    def _flush(self, prefix=""):
        raw = "".join(self.buf)
        self.buf = []
        # Links that span several blocks (whole-card links) are applied to the
        # first block that carries text, so the URL is not lost.
        opens, closes = raw.count("\x01"), raw.count("\x03")
        if self.link and not self.link_used:
            if opens == 0 and raw.strip():
                raw = f"\x01{self.link}\x02" + raw
                opens = 1
            if opens > closes and raw.replace("\x01" + self.link + "\x02", "").strip():
                raw += "\x03"
                self.link_used = True
        elif closes > opens and self.last_link and not self.link_used:
            raw = f"\x01{self.last_link}\x02" + raw
            self.link_used = True
        raw = re.sub(r"\x01([^\x02]*)\x02(.*?)\x03", lambda m: f"[{m.group(2).strip()}]({m.group(1)})" if m.group(2).strip() else "", raw, flags=re.S)
        raw = re.sub(r"[\x01\x02\x03]", "", re.sub(r"\x01[^\x02]*\x02", "", raw))
        text = re.sub(r"[ \t\r\n]+", " ", raw).strip()
        if not text:
            return
        if self.heading:
            text = "#" * self.heading + " " + text
        elif self.summary:
            text = "### " + text
        elif self.dt:
            text = "**" + text + "**"
        if self.quote:
            text = "> " + text
        indent = "  " * max(len(self.lists) - 1, 0)
        if self.lists and not self.heading:
            kind, _ = self.lists[-1]
            if kind == "ul":
                marker = "- "
            else:
                self.lists[-1][1] += 1
                marker = f"{self.lists[-1][1]}. "
            text = indent + marker + text
            self.out.append(text)
        else:
            self.out.append(text)
            self.out.append("")

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.skip_tag:
            if tag == self.skip_tag and tag not in VOID:
                self.skip_depth += 1
            return
        classes = (a.get("class") or "").split()
        if tag in SKIP or a.get("aria-hidden") == "true" or "marquee" in classes:
            if tag not in VOID:
                self.skip_tag, self.skip_depth = tag, 1
            return
        if tag in {"h1", "h2", "h3", "h4"}:
            self._flush()
            self.heading = int(tag[1])
        elif tag in {"ul", "ol"}:
            self._flush()
            self.lists.append([tag, 0])
        elif tag == "li":
            self._flush()
        elif tag == "summary":
            self._flush()
            self.summary = True
        elif tag == "dt":
            self._flush()
            self.dt = True
        elif tag == "blockquote":
            self._flush()
            self.quote = True
        elif tag in BLOCK:
            self._flush()
        elif tag == "br":
            self.buf.append(" ")
        elif tag in {"strong", "b"}:
            self.buf.append("**")
        elif tag in {"em", "i"}:
            self.buf.append("*")
        elif tag == "a" and a.get("href") and not a["href"].startswith(("tel:", "mailto:", "#")):
            self.link = urljoin(self.base, a["href"])
            self.link_used = False
            self.buf.append("\x01" + self.link + "\x02")
        elif tag == "a" and a.get("href", "").startswith(("tel:", "mailto:")):
            self.link = ""

    def handle_endtag(self, tag):
        if self.skip_tag:
            if tag == self.skip_tag:
                self.skip_depth -= 1
                if self.skip_depth == 0:
                    self.skip_tag = None
            return
        if tag in {"h1", "h2", "h3", "h4"}:
            self._flush()
            self.heading = None
        elif tag in {"ul", "ol"}:
            self._flush()
            if self.lists:
                self.lists.pop()
            if not self.lists:
                self.out.append("")
        elif tag == "li":
            self._flush()
        elif tag == "summary":
            self._flush()
            self.summary = False
        elif tag == "dt":
            self._flush()
            self.dt = False
        elif tag == "blockquote":
            self._flush()
            self.quote = False
        elif tag in BLOCK:
            self._flush()
        elif tag in {"strong", "b"}:
            self.buf.append("**")
        elif tag in {"em", "i"}:
            self.buf.append("*")
        elif tag == "a" and self.link is not None:
            if self.link:
                self.buf.append("\x03")
            self.last_link = self.link
            self.link = None

    def handle_data(self, data):
        if not self.skip_tag:
            self.buf.append(data)


def main_to_markdown(html, base_url):
    m = re.search(r"<main[^>]*>(.*?)</main>", html, re.S)
    parser = _MD(base_url)
    parser.feed(m.group(1) if m else html)
    parser._flush()
    text = "\n".join(parser.out)
    text = re.sub(r"\*\*\s*\*\*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text + "\n"
