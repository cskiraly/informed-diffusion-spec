#!/usr/bin/env python3
"""Pull the executable part of the protocol out of its Markdown.

Every ```python block of protocol.md is kept, in document order, under a comment that
names the section it came from, so a traceback points at the doc. The few spellings that are not
Python are rewritten by the NORMALISE table; each rewrite must match exactly once, so a doc edit that
removes or changes one fails here instead of silently running something else.

    python3 extract.py [DOC] [--out FILE]     # print or write the generated module
"""
import re
import sys
from pathlib import Path

DOC = Path(__file__).resolve().parent.parent / "protocol.md"

# (what the doc says, what runs, why). Every entry is a place where the doc is not yet Python, and
# a candidate for a fix in the doc itself. Empty since the nine fixes of 2026-10-03: the document's
# code runs as written.
NORMALISE = []


def blocks(text):
    """(section heading, code) for every python block, in order."""
    out, section = [], "preamble"
    for m in re.finditer(r"^(#{2,4} [^\n]*)$|^```python\n(.*?)^```", text, flags=re.M | re.S):
        if m.group(1):
            section = m.group(1).lstrip("#").strip()
        else:
            out.append((section, m.group(2)))
    return out


def generate(doc=DOC):
    text = Path(doc).read_text()
    parts = []
    for section, code in blocks(text):
        parts.append(f"# ---- {section}\n{code}")
    src = "\n".join(parts)
    for old, new, _why in NORMALISE:
        n = src.count(old)
        if n != 1:
            raise SystemExit(f"extract: expected one '{old}' in the doc's code, found {n}")
        src = src.replace(old, new)
    return src


def main(argv):
    doc, out = DOC, None
    args = list(argv)
    if "--out" in args:
        i = args.index("--out")
        out = args[i + 1]
        del args[i:i + 2]
    if args:
        doc = args[0]
    src = generate(doc)
    compile(src, str(doc), "exec")          # fails loudly on anything that is still not Python
    if out:
        Path(out).write_text(src)
    else:
        sys.stdout.write(src)


if __name__ == "__main__":
    main(sys.argv[1:])
