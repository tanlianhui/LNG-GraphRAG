#!/usr/bin/env python3
"""
rebuild_transcriptions.py — re-transcribe VODs whose _combined.txt is broken.

Old transcriptions were produced before simple_asr.py enforced a 30s chunk cap:
a whole stream became ONE chunk, and Whisper's ~448-token output cap truncated
multi-hour audio down to a few characters (e.g. a 4.8h file → "你"). This rebuild:

  1. Finds every *_combined.txt with a chunk longer than --threshold seconds.
  2. Ensures the source WAV exists (downloads from the videos.csv URL if missing).
  3. Re-runs simple_asr.py (30s cap + beam search + keyword prompt) to overwrite it.

Resumable: a file whose largest chunk is already <= --threshold is skipped, so
you can stop/restart freely. Cleanup (Taiwan-LLM) + CJK spacing are SEPARATE
later steps — run postprocess_transcriptions.py then fix_cjk_spacing.py after.

Usage:
    python rebuild_transcriptions.py --dry-run
    python rebuild_transcriptions.py                       # download + re-ASR all
    python rebuild_transcriptions.py --no-download         # only files that already have a WAV
    python rebuild_transcriptions.py --filter 2014         # subset by filename
    python rebuild_transcriptions.py --limit 5             # first N (for a test batch)
"""
import os
import re
import sys
import csv
import argparse
import subprocess
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TRANSCRIPTIONS = Path('./transcriptions')
VODS = Path('./VODs')
VIDEOS_CSV = VODS / 'videos.csv'
SIMPLE_ASR = Path(__file__).resolve().parent / 'simple_asr.py'

_HEADER = re.compile(r'=== Chunk \d+ \[([0-9.]+)s - ([0-9.]+)s\]')


def _normalize_title(s: str) -> str:
    """Same normalization web_app uses: NFKC + keep only alphanumerics/CJK.
    Bridges filename vs videos.csv drift (e.g. '/' -> '⧸' U+29F8)."""
    s = unicodedata.normalize('NFKC', s or '').lower()
    return ''.join(c for c in s if c.isalnum())


def max_chunk_seconds(combined_path: Path) -> float:
    """Largest (end - start) across chunk headers; 0 if none/unreadable."""
    try:
        text = combined_path.read_text(encoding='utf-8')
    except Exception:
        return 0.0
    m = 0.0
    for s, e in _HEADER.findall(text):
        try:
            d = float(e) - float(s)
            if d > m:
                m = d
        except ValueError:
            continue
    return m


def load_url_map() -> dict:
    """base-title (normalized) -> url from videos.csv."""
    out = {}
    if not VIDEOS_CSV.exists():
        return out
    with open(VIDEOS_CSV, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            title = (row.get('title') or '').strip()
            url = (row.get('url') or '').strip()
            if title and url:
                out.setdefault(_normalize_title(title), url)
    return out


def find_broken(threshold: float, filter_str: str):
    """List (base, combined_path) for files with a chunk > threshold seconds."""
    broken = []
    for c in sorted(TRANSCRIPTIONS.glob('*_combined.txt')):
        if filter_str and filter_str not in c.name:
            continue
        if max_chunk_seconds(c) > threshold:
            broken.append((c.stem[:-len('_combined')], c))
    return broken


def ensure_wav(base: str, url_map: dict, allow_download: bool):
    """Return (wav_path, downloaded_bool). wav_path is None on failure.
    downloaded_bool is True only when we fetched it this run (caller may delete it
    afterwards to bound disk usage; pre-existing WAVs are preserved)."""
    wav = VODS / f'{base}.wav'
    if wav.exists() and wav.stat().st_size > 0:
        return wav, False
    if not allow_download:
        return None, False
    url = url_map.get(_normalize_title(base))
    if not url:
        print(f'    no URL in videos.csv for "{base[:60]}" — cannot download')
        return None, False
    print(f'    downloading {url} ...')
    try:
        from VODs.download_from_youtube import download_from_youtube
        ok, path = download_from_youtube(url)
    except Exception as e:
        print(f'    download error: {e}')
        ok, path = False, None
    if not ok or not path:
        # yt-dlp's FFmpegExtractAudio can report "audio conversion failed" on some
        # sources (e.g. PCM-in-MP4) yet still (a) write a valid WAV anyway, or
        # (b) leave the raw media behind. Handle both before giving up.
        if wav.exists() and wav.stat().st_size > 0:
            print('    WAV present despite reported failure — using it')
            return wav, True
        salvaged = salvage_with_ffmpeg(base, wav)
        if salvaged:
            print('    salvaged via ffmpeg from downloaded source')
            return salvaged, True
        print('    download failed')
        return None, False
    path = Path(path)
    # Keep the filename aligned with the original base so re-ASR overwrites the
    # right _combined.txt (yt-dlp may sanitize the title slightly differently).
    if path.name != wav.name:
        try:
            if wav.exists():
                path.unlink()
            else:
                path.rename(wav)
            return (wav if wav.exists() else path), True
        except Exception:
            return path, True
    return wav, True


def salvage_with_ffmpeg(base: str, wav: Path) -> Path | None:
    """Convert a leftover downloaded source media for `base` (any non-.wav file
    yt-dlp left in VODs, incl. extensionless) into a 16k mono WAV via a direct
    ffmpeg call. Returns the WAV path on success, else None."""
    cands = [p for p in VODS.iterdir()
             if p.is_file() and p.suffix.lower() != '.wav'
             and (p.stem == base or p.name == base)]
    if not cands:
        # looser match: filename starts with base (yt-dlp may append a format id)
        cands = [p for p in VODS.iterdir()
                 if p.is_file() and p.suffix.lower() != '.wav'
                 and p.name.startswith(base) and p.stat().st_size > 100_000]
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    for src in cands:
        r = subprocess.run(
            ['ffmpeg', '-y', '-i', str(src), '-ac', '1', '-ar', '16000', str(wav)],
            capture_output=True)
        if r.returncode == 0 and wav.exists() and wav.stat().st_size > 0:
            try:
                src.unlink()   # drop the source media once converted
            except OSError:
                pass
            return wav
    return None


def reasr(wav: Path) -> bool:
    """Run simple_asr.py on the WAV in a fresh subprocess (CUDA isolation)."""
    env = dict(os.environ)
    env.setdefault('ASR_NUM_BEAMS', '5')          # beam search quality
    env.setdefault('PYTHONIOENCODING', 'utf-8')
    r = subprocess.run([sys.executable, str(SIMPLE_ASR), str(wav), '--suffix', '_combined'],
                       env=env, check=False)
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--threshold', type=float, default=60.0,
                    help='A file is "broken" if any chunk exceeds this many seconds (default 60)')
    ap.add_argument('--no-download', action='store_true', help='Skip files whose WAV is missing')
    ap.add_argument('--keep-wav', action='store_true', help='Do not delete downloaded WAVs after ASR')
    ap.add_argument('--filter', default='', help='Only files whose name contains this string')
    ap.add_argument('--limit', type=int, default=0, help='Process at most N files (0 = all)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    broken = find_broken(args.threshold, args.filter)
    print(f'Broken files (chunk > {args.threshold:.0f}s): {len(broken)}')
    if args.limit:
        broken = broken[:args.limit]
        print(f'Limited to first {len(broken)}')

    url_map = load_url_map()
    print(f'videos.csv URL entries: {len(url_map)}\n')

    if args.dry_run:
        for base, c in broken:
            wav = VODS / f'{base}.wav'
            has_wav = wav.exists()
            has_url = _normalize_title(base) in url_map
            tag = 'WAV' if has_wav else ('URL' if has_url else 'MISSING')
            print(f'  [{tag}] {base[:70]}')
        return 0

    ok = failed = skipped = 0
    for i, (base, c) in enumerate(broken, 1):
        print(f'[{i}/{len(broken)}] {base[:65]}')
        # Resumability: already re-ASR'd (all chunks small) → skip.
        if max_chunk_seconds(c) <= args.threshold:
            print('    already rebuilt — skip')
            skipped += 1
            continue
        wav, downloaded = ensure_wav(base, url_map, allow_download=not args.no_download)
        if wav is None:
            print('    no WAV available — skip')
            failed += 1
            continue
        ok_flag = reasr(wav)
        if ok_flag:
            print(f'    re-ASR ok (max chunk now {max_chunk_seconds(c):.0f}s)')
            ok += 1
        else:
            print('    re-ASR FAILED (see simple_asr output above)')
            failed += 1
        # Disk hygiene (E: is tight): ALWAYS delete a WAV we downloaded this run —
        # even on failure — so failed ASR can't leak audio and fill the drive (that
        # bug filled E: to 0). Pre-existing WAVs are deleted only on success (so a
        # transient failure doesn't destroy the source), which also honours the
        # "remove transcribed audio files" request. --keep-wav disables all deletion.
        if not args.keep_wav and (downloaded or ok_flag):
            try:
                Path(wav).unlink()
                print('    deleted WAV')
            except Exception as e:
                print(f'    could not delete WAV: {e}')

    print(f'\nDone. rebuilt: {ok}, skipped: {skipped}, failed/unavailable: {failed}')
    print('Next: python postprocess_transcriptions.py  (delete stale _postprocessed first),')
    print('      then python fix_cjk_spacing.py')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
