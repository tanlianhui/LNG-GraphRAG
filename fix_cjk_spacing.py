#!/usr/bin/env python3
"""
fix_cjk_spacing.py — insert missing spaces at CJK↔Latin boundaries.

The Taiwan-LLM cleanup pass runs through a BPE tokenizer whose
clean_up_tokenization_spaces step strips spaces before punctuation and can drop
the space between Chinese and English/number runs (e.g. "random的" instead of
"random 的", "google他" instead of "google 他"). This restores that spacing.

Idempotent: a boundary that already has a space is left alone, so re-running is
safe (and safe to run on files the postprocess job has already finished while
the job is still processing other files).

Chunk header lines ("=== Chunk N [..s - ..s] ===") are left untouched so the
"..s" timestamps aren't mangled.

Usage:
    python fix_cjk_spacing.py                       # all _postprocessed.txt, in place
    python fix_cjk_spacing.py --filter "2024"
    python fix_cjk_spacing.py --suffix _combined    # target a different suffix
    python fix_cjk_spacing.py --dry-run             # show counts, write nothing
"""

import re
import sys
import argparse
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TRANSCRIPTIONS = Path('./transcriptions')

# CJK ideograph ranges we treat as "Chinese". Kept deliberately to Han so we
# don't insert spaces around CJK punctuation (，。？！ etc.).
_CJK = r'一-鿿㐀-䶿'
# The Latin side: ASCII letters (+digits unless --letters-only). Excludes
# punctuation so we never turn "他?" into "他 ?".
_HEADER = re.compile(r'^=== Chunk \d+ \[')


def _compile(letters_only: bool):
    latin = r'A-Za-z' if letters_only else r'A-Za-z0-9'
    return (re.compile(rf'([{_CJK}])([{latin}])'),
            re.compile(rf'([{latin}])([{_CJK}])'))


# Module-level default (letters + digits) so fix_text/fix_line work without args.
_CJK_THEN_LATIN, _LATIN_THEN_CJK = _compile(False)


def fix_line(line: str, patterns=None) -> str:
    if _HEADER.match(line):
        return line
    cjk_latin, latin_cjk = patterns or (_CJK_THEN_LATIN, _LATIN_THEN_CJK)
    line = cjk_latin.sub(r'\1 \2', line)
    line = latin_cjk.sub(r'\1 \2', line)
    return line


def fix_text(text: str, patterns=None) -> tuple[str, int]:
    """Return (fixed_text, num_spaces_inserted)."""
    out_lines = []
    inserted = 0
    for line in text.splitlines():
        fixed = fix_line(line, patterns)
        # Count net length gain = spaces added (each insertion adds one char).
        inserted += len(fixed) - len(line)
        out_lines.append(fixed)
    # Preserve trailing newline if the original had one.
    tail = '\n' if text.endswith('\n') else ''
    return '\n'.join(out_lines) + tail, inserted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--filter', default='',           help='Filename substring filter')
    parser.add_argument('--suffix', default='_postprocessed',
                        help='Target file suffix (default: _postprocessed)')
    parser.add_argument('--letters-only', action='store_true',
                        help='Only space CJK↔letters; leave digits tight (e.g. keep "5顆")')
    parser.add_argument('--dry-run', action='store_true', help='Report only, write nothing')
    args = parser.parse_args()

    patterns = _compile(args.letters_only)

    files = sorted(TRANSCRIPTIONS.glob(f'*{args.suffix}.txt'))
    if args.filter:
        files = [f for f in files if args.filter in f.name]

    print(f'Found {len(files)} file(s) with suffix "{args.suffix}" matching "{args.filter}"')

    changed = total_inserted = 0
    for i, path in enumerate(files, 1):
        text = path.read_text(encoding='utf-8')
        fixed, inserted = fix_text(text, patterns)
        if inserted:
            changed += 1
            total_inserted += inserted
            tag = 'would fix' if args.dry_run else 'fixed'
            print(f'[{i}/{len(files)}] {tag} +{inserted} spaces  {path.name[:70]}')
            if not args.dry_run:
                path.write_text(fixed, encoding='utf-8')

    verb = 'Would insert' if args.dry_run else 'Inserted'
    print(f'\nDone. {verb} {total_inserted} space(s) across {changed}/{len(files)} file(s).')


if __name__ == '__main__':
    main()
