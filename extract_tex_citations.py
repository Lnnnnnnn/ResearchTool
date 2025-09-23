#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Extract citation keys from LaTeX .tex files and collect matching entries
from .bib files into a consolidated .bib output.
- Robust to various cite commands (\cite, \citep, \citet, \textcite, \parencite, \autocite, etc.)
- Handles optional arguments (\cite[see][ch.2]{key})
- Handles multiple keys inside one cite (\cite{a,b,c})
- Parses .bib with proper brace nesting (safe for { } in fields)

Usage examples:
  python extract_tex_citations.py --tex path/to/paper.tex --bib-dir path/to/bibs --out extracted.bib
  python extract_tex_citations.py --tex-dir ./texsrc --bib ./refs1.bib ./refs2.bib -o collected.bib
"""

import argparse
import re
from pathlib import Path
from typing import List, Set, Dict, Tuple

CITE_CMD_PATTERN = re.compile(
    r"""
    \\                               # backslash
    (?:[Cc]ite|[Pp]arencite|[Tt]extcite|[Aa]utocite|[Ss]martcite|[Ff]ootcite
       |[Nn]ocite|[Cc]iteauthor|[Cc]itealp|[Cc]iteyear|[Cc]iteyearpar
       |[Cc]itet|[Cc]itep|[Cc]itealt|[Cc]itealp|[Cc]iteauthor*)  # common variants
    (?:\s*\[[^\]]*\])*\s*            # zero or more optional args [..]
    \{(?P<keys>[^}]*)\}              # mandatory {key1,key2,...}
    """,
    re.VERBOSE | re.DOTALL,
)

def find_tex_files(tex: List[str], tex_dir: str) -> List[Path]:
    files: List[Path] = []
    if tex:
        for p in tex:
            path = Path(p)
            if path.is_file() and path.suffix.lower() == ".tex":
                files.append(path)
            elif path.is_dir():
                files.extend(path.rglob("*.tex"))
            else:
                # allow glob patterns
                files.extend(Path().glob(p))
    if tex_dir:
        root = Path(tex_dir)
        if root.is_dir():
            files.extend(root.rglob("*.tex"))
    # unique, keep stable order
    seen = set()
    ordered = []
    for f in files:
        if f.resolve() not in seen:
            ordered.append(f)
            seen.add(f.resolve())
    return ordered

def extract_cite_keys_from_text(text: str) -> Set[str]:
    keys: Set[str] = set()
    for m in CITE_CMD_PATTERN.finditer(text):
        group = m.group("keys")
        if not group:
            continue
        for k in group.split(","):
            k = k.strip()
            # ignore empty or weird things
            if k:
                keys.add(k)
    return keys

def extract_cite_keys_from_files(files: List[Path], encoding="utf-8") -> Set[str]:
    all_keys: Set[str] = set()
    for f in files:
        try:
            txt = f.read_text(encoding=encoding, errors="ignore")
        except Exception as e:
            print(f"[WARN] Could not read {f}: {e}")
            continue
        keys = extract_cite_keys_from_text(txt)
        if keys:
            print(f"[INFO] {f}: found {len(keys)} unique keys")
        all_keys.update(keys)
    print(f"[INFO] Total unique citation keys: {len(all_keys)}")
    return all_keys

def find_bib_files(bib: List[str], bib_dir: str) -> List[Path]:
    files: List[Path] = []
    if bib:
        for p in bib:
            path = Path(p)
            if path.is_file() and path.suffix.lower() == ".bib":
                files.append(path)
            elif path.is_dir():
                files.extend(path.rglob("*.bib"))
            else:
                files.extend(Path().glob(p))
    if bib_dir:
        root = Path(bib_dir)
        if root.is_dir():
            files.extend(root.rglob("*.bib"))
    # unique
    seen = set()
    ordered = []
    for f in files:
        if f.resolve() not in seen:
            ordered.append(f)
            seen.add(f.resolve())
    return ordered

def parse_bib_entries(bib_path: Path, encoding="utf-8") -> Dict[str, str]:
    """
    Minimal BibTeX parser:
    - Detects entry start by '@' and reads until matching closing '}' with brace depth tracking.
    - Returns dict: key -> full entry text (including leading @...{key, ...})
    """
    text = bib_path.read_text(encoding=encoding, errors="ignore")
    entries: Dict[str, str] = {}
    i = 0
    n = len(text)
    while i < n:
        # find next '@'
        at = text.find('@', i)
        if at == -1:
            break
        # find the first '{' after '@'
        lb = text.find('{', at)
        if lb == -1:
            break
        # extract key between '{' and following comma
        comma = text.find(',', lb)
        if comma == -1:
            # malformed, skip
            i = lb + 1
            continue
        key = text[lb + 1:comma].strip()
        # track braces from lb to find end of entry
        depth = 0
        j = lb
        while j < n:
            c = text[j]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    # entry ends at j
                    entry = text[at:j + 1]
                    if key:
                        entries.setdefault(key, entry.strip())
                    i = j + 1
                    break
            j += 1
        else:
            # no closing brace found
            break
    return entries

def load_all_bib_entries(bib_files: List[Path]) -> Dict[str, Tuple[Path, str]]:
    """
    Return mapping: key -> (source_path, entry_text)
    Later files do NOT overwrite earlier ones (first-hit wins).
    """
    all_entries: Dict[str, Tuple[Path, str]] = {}
    for bf in bib_files:
        try:
            parsed = parse_bib_entries(bf)
        except Exception as e:
            print(f"[WARN] Could not parse {bf}: {e}")
            continue
        count_before = len(all_entries)
        for k, v in parsed.items():
            if k not in all_entries:
                all_entries[k] = (bf, v)
        print(f"[INFO] {bf}: loaded {len(parsed)} entries "
              f"({len(all_entries) - count_before} new)")
    print(f"[INFO] Total unique .bib entries available: {len(all_entries)}")
    return all_entries

def write_output_bib(keys: Set[str], entries: Dict[str, Tuple[Path, str]], out_path: Path) -> List[str]:
    found = []
    missing = []
    with out_path.open("w", encoding="utf-8") as f:
        f.write("% Generated by extract_tex_citations.py\n\n")
        for k in sorted(keys):
            if k in entries:
                _, entry = entries[k]
                f.write(entry.strip())
                f.write("\n\n")
                found.append(k)
            else:
                missing.append(k)
    print(f"[INFO] Wrote {len(found)} entries to {out_path}")
    if missing:
        print(f"[WARN] {len(missing)} keys missing (not found in provided .bib files)")
    return missing

def main():
    ap = argparse.ArgumentParser(description="Extract LaTeX cite keys and collect matching .bib entries.")
    ap.add_argument("--tex", nargs="*", default=[], help="One or more .tex files, directories, or glob patterns")
    ap.add_argument("--tex-dir", default="", help="Directory containing .tex (searched recursively)")
    ap.add_argument("--bib", nargs="*", default=[], help="One or more .bib files, directories, or glob patterns")
    ap.add_argument("--bib-dir", default="", help="Directory containing .bib (searched recursively)")
    ap.add_argument("-o", "--out", default="extracted.bib", help="Output .bib file (default: extracted.bib)")
    ap.add_argument("--print-keys", action="store_true", help="Print unique keys found from .tex and exit")
    args = ap.parse_args()

    tex_files = find_tex_files(args.tex, args.tex_dir)
    if not tex_files:
        print("[ERROR] No .tex files found. Use --tex or --tex-dir.")
        return

    keys = extract_cite_keys_from_files(tex_files)

    if args.print_keys:
        for k in sorted(keys):
            print(k)
        return

    bib_files = find_bib_files(args.bib, args.bib_dir)
    if not bib_files:
        print("[ERROR] No .bib files found. Use --bib or --bib-dir.")
        return

    all_entries = load_all_bib_entries(bib_files)
    missing = write_output_bib(keys, all_entries, Path(args.out))

    # Also write a small report next to the output .bib
    report_path = Path(args.out).with_suffix(".report.txt")
    with report_path.open("w", encoding="utf-8") as rf:
        rf.write(f"Total keys in .tex: {len(keys)}\n")
        rf.write(f"Found in .bib: {len(keys) - len(missing)}\n")
        rf.write(f"Missing: {len(missing)}\n\n")
        if missing:
            rf.write("Missing keys:\n")
            for k in sorted(missing):
                rf.write(f"  - {k}\n")
    print(f"[INFO] Report saved to {report_path}")

if __name__ == "__main__":
    main()
