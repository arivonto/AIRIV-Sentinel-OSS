#!/usr/bin/env python3
"""Validate AIRIV Sentinel project documentation without third-party packages."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
INDEX = ROOT / "index.html"

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

DISCLOSURE_PATTERNS = {
    "user-specific absolute home path": re.compile(r"/home/[A-Za-z0-9._-]+/"),
    "private AIRIV state path": re.compile(r"/var/lib/airiv-sentinel-[A-Za-z0-9._/-]+"),
    "private AIRIV authorization path": re.compile(r"/etc/airiv-sentinel/[A-Za-z0-9._/-]+\.json"),
    "internal host command ref": re.compile(r"\bhost/[A-Za-z0-9._/-]*command\b"),
    "named private runner identity": re.compile(r"self-hosted runner\s*:\s*[A-Za-z0-9._-]+", re.I),
}

REQUIRED_PHRASES = (
    "Fail-closed Autonomous Commander",
    "AIRIV Sentinel Roadmap",
    "Contract > Implementation > Local Preference",
)


def fail(message: str) -> None:
    raise SystemExit(f"PROJECT_DOCS_VALIDATION=FAIL: {message}")


class StrictHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.ids: set[str] = set()
        self.hrefs: list[str] = []

    def _attrs(self, attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = self._attrs(attrs)
        element_id = values.get("id")
        if element_id:
            if element_id in self.ids:
                fail(f"duplicate HTML id: {element_id}")
            self.ids.add(element_id)
        href = values.get("href")
        if href:
            self.hrefs.append(href)
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        if not self.stack:
            fail(f"unexpected closing HTML tag: {tag}")
        expected = self.stack.pop()
        if expected != tag:
            fail(f"HTML nesting mismatch: expected </{expected}> but found </{tag}>")

    def close(self) -> None:
        super().close()
        if self.stack:
            fail("unclosed HTML tag(s): " + ", ".join(self.stack[-5:]))


def relative_target_exists(raw: str, source: Path) -> bool:
    parsed = urlsplit(raw)
    if parsed.scheme or raw.startswith("//"):
        return True
    if raw.startswith("#"):
        return True
    target_text = unquote(parsed.path)
    if not target_text:
        return True
    target = (source.parent / target_text).resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        return False
    return target.exists()


def validate_markdown_links(text: str) -> None:
    links = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text)
    missing = [link for link in links if not relative_target_exists(link.strip(), README)]
    if missing:
        fail("README has missing/unsafe relative link(s): " + ", ".join(sorted(set(missing))))


def validate_html(text: str) -> None:
    parser = StrictHTML()
    parser.feed(text)
    parser.close()

    required_ids = {"top", "snapshot", "evolution", "architecture", "specs", "install", "security", "roadmap"}
    missing_ids = sorted(required_ids - parser.ids)
    if missing_ids:
        fail("index.html missing required section id(s): " + ", ".join(missing_ids))

    for href in parser.hrefs:
        if href.startswith("#"):
            anchor = href[1:]
            if anchor and anchor not in parser.ids:
                fail(f"index.html references missing anchor: {href}")
            continue
        if not relative_target_exists(href, INDEX):
            fail(f"index.html has missing/unsafe relative link: {href}")


def validate_disclosure_surface(path: Path, text: str) -> None:
    for label, pattern in DISCLOSURE_PATTERNS.items():
        if pattern.search(text):
            fail(f"{path.name} exposes {label}")


def main() -> int:
    if not README.is_file():
        fail("README.md missing")
    readme = README.read_text(encoding="utf-8")
    for phrase in REQUIRED_PHRASES:
        if phrase not in readme:
            fail(f"README.md missing lock phrase: {phrase}")
    validate_markdown_links(readme)
    validate_disclosure_surface(README, readme)

    public_snapshot = "Clean open-source distribution." in readme
    if INDEX.exists():
        index = INDEX.read_text(encoding="utf-8")
        for phrase in REQUIRED_PHRASES[:2]:
            if phrase not in index:
                fail(f"index.html missing lock phrase: {phrase}")
        validate_html(index)
        validate_disclosure_surface(INDEX, index)
    elif not public_snapshot:
        fail("index.html missing from canonical project tree")

    print("PROJECT_DOCS_README_LINKS=PASS")
    print("PROJECT_DOCS_DISCLOSURE_GUARD=PASS")
    print("PROJECT_DOCS_HTML=PASS" if INDEX.exists() else "PROJECT_DOCS_HTML=NOT_APPLICABLE_PUBLIC_SNAPSHOT")
    print("PROJECT_DOCS_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
