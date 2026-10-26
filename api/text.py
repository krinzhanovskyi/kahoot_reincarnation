"""Convert API rich text to readable plain text without evaluating HTML."""

import re
from html.parser import HTMLParser


class _PlainTextParser(HTMLParser):
    INLINE = {"b", "strong", "i", "em", "u", "s", "span", "a", "font", "code"}
    BLOCK = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "blockquote", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = None
        self.has_image = False

    def handle_starttag(self, tag, attrs):
        if self.hidden:
            return
        if tag in {"script", "style"}:
            self.hidden = tag
        elif tag == "br" or tag in self.BLOCK:
            self.parts.append("\n")
        elif tag in {"sup", "sub"}:
            self.parts.append("^(" if tag == "sup" else "_(")
        elif tag == "img":
            self.has_image = True
            self.parts.append("[image]")
        elif tag not in self.INLINE:
            # Preserve unknown literal markup, e.g. programming quiz text.
            self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden:
                self.hidden = None
            return
        if tag in self.BLOCK:
            self.parts.append("\n")
        elif tag in {"sup", "sub"}:
            self.parts.append(")")
        elif tag not in self.INLINE and tag not in {"br", "img"}:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean_text(value):
    if not isinstance(value, str):
        return ""
    parser = _PlainTextParser()
    parser.feed(value)
    parser.close()
    text = "".join(parser.parts).replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def contains_image(value):
    if not isinstance(value, str):
        return False
    parser = _PlainTextParser()
    parser.feed(value)
    parser.close()
    return parser.has_image
