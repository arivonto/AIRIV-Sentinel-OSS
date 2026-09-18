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
ROADMAP = ROOT / "AIRIV_SENTINEL_ROADMAP.md"
STATUS_REGISTRY = ROOT / "docs" / "AIRIV_SENTINEL_STATUS_CONTRACT_REGISTRY.md"
LANE_REGISTRY = ROOT / "docs" / "AIRIV_SENTINEL_PARALLEL_LANE_REGISTRY.md"

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

# Project-level summaries must not become a map of one trusted production host.
# Patterns describe private-topology classes rather than embedding current values.
DISCLOSURE_PATTERNS = {
    "user-specific absolute home path": re.compile(r"/home/[A-Za-z0-9._-]+/"),
    "private AIRIV state path": re.compile(r"/var/lib/airiv-sentinel-[A-Za-z0-9._/-]+"),
    "private AIRIV authorization path": re.compile(r"/etc/airiv-sentinel/[A-Za-z0-9._/-]+\.json"),
    "internal host command ref": re.compile(r"\bhost/[A-Za-z0-9._/-]*command\b"),
    "named private runner identity": re.compile(r"self-hosted runner\s*:\s*[A-Za-z0-9._-]+", re.I),
}

REQUIRED_PHRASES = (
    "Linux-first Autonomous Multi-AI Engineering Desktop",
    "One Mission.",
    "Any AI.",
    "Linux First.",
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

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
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


def validate_markdown_links(text: str, source: Path) -> None:
    links = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text)
    missing = [link for link in links if not relative_target_exists(link.strip(), source)]
    if missing:
        fail(
            f"{source.relative_to(ROOT)} has missing/unsafe relative link(s): "
            + ", ".join(sorted(set(missing)))
        )


def validate_html(text: str) -> None:
    parser = StrictHTML()
    parser.feed(text)
    parser.close()

    required_ids = {
        "top", "snapshot", "surfaces", "web-console", "domains", "evolution", "architecture",
        "specs", "install", "security", "roadmap",
    }
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
            fail(f"{path.relative_to(ROOT)} exposes {label}")


def validate_status_registry(registry: str) -> None:
    if "../AIRIV_SENTINEL_ROADMAP.md" not in registry:
        fail("status/contract registry does not reference canonical roadmap")

    if "../baseline/AIRIV_SENTINEL_V1_BASELINE_FREEZE.md" not in registry:
        fail("status/contract registry does not reference V1 baseline freeze")

    if "AIRIV_SENTINEL_PARALLEL_LANE_REGISTRY.md" not in registry:
        fail("status/contract registry does not reference parallel lane registry")

    if "Contract > Implementation > Roadmap > Local Preference" not in registry:
        fail("status/contract registry missing canonical precedence rule")


def validate_lane_registry(registry: str) -> None:
    if "Candidate state does not equal canonical state." not in registry:
        fail("parallel lane registry missing noncanonical-state guard")

    for lane in range(1, 8):
        if f"Lane {lane}" not in registry:
            fail(f"parallel lane registry missing Lane {lane}")

    if "PRODUCTION_EFFECT=NONE" not in registry:
        fail("parallel lane registry missing production-effect boundary")


def main() -> int:
    base_required = (README, INDEX, ROADMAP)
    missing_base = [str(path.relative_to(ROOT)) for path in base_required if not path.is_file()]
    if missing_base:
        fail("required project document(s) missing: " + ", ".join(missing_base))

    readme = README.read_text(encoding="utf-8")
    index = INDEX.read_text(encoding="utf-8")
    roadmap = ROADMAP.read_text(encoding="utf-8")
    public_snapshot = "Clean open-source distribution." in readme

    if not public_snapshot:
        canonical_required = (STATUS_REGISTRY, LANE_REGISTRY)
        missing_canonical = [
            str(path.relative_to(ROOT))
            for path in canonical_required
            if not path.is_file()
        ]
        if missing_canonical:
            fail(
                "canonical source missing required project document(s): "
                + ", ".join(missing_canonical)
            )

    status_registry = (
        STATUS_REGISTRY.read_text(encoding="utf-8")
        if STATUS_REGISTRY.is_file()
        else None
    )
    lane_registry = (
        LANE_REGISTRY.read_text(encoding="utf-8")
        if LANE_REGISTRY.is_file()
        else None
    )

    for phrase in REQUIRED_PHRASES:
        if phrase not in readme:
            fail(f"README.md missing lock phrase: {phrase}")
    for phrase in REQUIRED_PHRASES[:2]:
        if phrase not in index:
            fail(f"index.html missing lock phrase: {phrase}")

    validate_markdown_links(readme, README)
    validate_markdown_links(roadmap, ROADMAP)
    validate_html(index)

    disclosure_surfaces = [
        (README, readme),
        (INDEX, index),
        (ROADMAP, roadmap),
    ]

    if status_registry is not None:
        validate_markdown_links(status_registry, STATUS_REGISTRY)
        validate_status_registry(status_registry)
        disclosure_surfaces.append((STATUS_REGISTRY, status_registry))

    if lane_registry is not None:
        validate_markdown_links(lane_registry, LANE_REGISTRY)
        validate_lane_registry(lane_registry)
        disclosure_surfaces.append((LANE_REGISTRY, lane_registry))

    for path, text in disclosure_surfaces:
        validate_disclosure_surface(path, text)

    if public_snapshot and "Curated public domain:" not in index:
        fail("public index.html missing curated-public notice")

    print("PROJECT_DOCS_README_LINKS=PASS")
    print("PROJECT_DOCS_ROADMAP_LINKS=PASS")
    if status_registry is not None:
        print("PROJECT_DOCS_STATUS_REGISTRY=PASS")
    else:
        print("PROJECT_DOCS_STATUS_REGISTRY_SCOPE=CANONICAL_ONLY")
    if lane_registry is not None:
        print("PROJECT_DOCS_PARALLEL_LANE_REGISTRY=PASS")
    else:
        print("PROJECT_DOCS_PARALLEL_LANE_REGISTRY_SCOPE=CANONICAL_ONLY")
    print("PROJECT_DOCS_DISCLOSURE_GUARD=PASS")
    print("PROJECT_DOCS_HTML=PASS")
    print("PROJECT_DOCS_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
