"""
postprocess_transcriptions.py — LLM-clean existing _combined.txt transcriptions.

Problems fixed:
  1. Hallucinated repetitions  (喔喔喔喔… × 300, 那個那個那個…)
  2. Proper-noun corrections   (channel members, game titles)
  3. Punctuation insertion      (full-stops, commas for readability)

Output: transcriptions/<title>_postprocessed.txt
  — same chunk format as _combined.txt so the ingest pipeline can use it.

Usage:
    python postprocess_transcriptions.py                   # all _combined.txt
    python postprocess_transcriptions.py --filter "2024"
    python postprocess_transcriptions.py --skip-existing
    python postprocess_transcriptions.py --dry-run
    python postprocess_transcriptions.py --source merged   # use _merged.txt if present
"""

import re
import os
import sys
import argparse
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TRANSCRIPTIONS = Path('./transcriptions')

# ── regex: detect and collapse repetition artifacts ──────────────────────────
# Matches the same CJK char repeated 4+ times OR "那個" repeated 3+ times.
_REP_CJK  = re.compile(r'([一-鿿＀-￯])\1{3,}')
_REP_NAGE = re.compile(r'(那個){3,}')


def cheap_clean(text: str) -> str:
    """Rule-based pre-clean before hitting the LLM (saves tokens, reduces noise)."""
    # Collapse runs of the same CJK char → max 2
    text = _REP_CJK.sub(lambda m: m.group(1) * 2, text)
    # Collapse 那個那個那個… → 那個那個
    text = _REP_NAGE.sub('那個那個', text)
    # Strip stray ASCII error messages that slipped through
    text = re.sub(r'\[Error in chunk \d+:.*?\]', '', text, flags=re.DOTALL)
    return text.strip()


# ── LLM setup ─────────────────────────────────────────────────────────────────

def get_llm():
    backend = os.getenv('NL_QUERY_LLM', 'openai').strip().lower()
    if backend == 'ollama':
        from langchain_ollama import ChatOllama
        mdl = os.getenv('OLLAMA_NL_MODEL', 'llama3.2')
        return ChatOllama(model=mdl, temperature=0.1,
                          timeout=int(os.getenv('OLLAMA_TIMEOUT', '120')),
                          num_ctx=int(os.getenv('OLLAMA_NUM_CTX', '8192')))
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=os.getenv('OPENAI_NL_MODEL', 'gpt-4o-mini'), temperature=0.1)


SYSTEM_PROMPT = """\
你是LNG Gaming頻道直播字幕的後製專家。
頻道成員（常見名字）：小六、六探、鳥屎、Leggy、巴毛、八毛、老王、大毛、展邱、梁兄、乃哥、阿旺、托老師、素雲、天神、Fick、FIG。
常見遊戲：英雄聯盟、快打旋風、暗黑破壞神、派對動物、TFT、Valorant、魔獸世界。
內容為台灣華語直播對話，夾雜英文、台語。

請對以下ASR辨識文字進行後製清理，規則如下：
1. 移除或縮短明顯重複字符（如「喔喔喔喔…」超過2個、「那個那個那個…」超過2次），保留自然語氣最多2個
2. 依上下文修正可能被ASR誤辨識的頻道成員名字與遊戲名稱
3. 加入適當標點符號（逗號、句號、問號），讓文字易讀但不改變語氣
4. 保留原本的說話風格、台語、英文夾雜，不要翻譯或重寫
5. 若原文無法辨識或完全是錯誤訊息，回覆空字串
6. 只回覆清理後的文字，不加說明、不加標題"""

USER_TEMPLATE = "原始文字：\n{text}\n\n清理後："


def llm_clean_chunk(llm, text: str) -> str:
    if not text.strip():
        return ''
    pre = cheap_clean(text)
    if not pre:
        return ''
    prompt = USER_TEMPLATE.format(text=pre[:3000])
    try:
        resp = llm.invoke([
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user',   'content': prompt},
        ])
        result = re.sub(r'<think>.*?</think>', '', resp.content, flags=re.DOTALL).strip()
        return result or pre
    except Exception as e:
        print(f'    LLM error: {e} — keeping pre-cleaned text')
        return pre


# ── File helpers ───────────────────────────────────────────────────────────────

def parse_chunks(path: Path) -> list[tuple[float, float, str]]:
    header = re.compile(r'=== Chunk \d+ \[(\d+\.?\d*)s - (\d+\.?\d*)s\]')
    chunks, cur_s, cur_e, cur_lines = [], None, None, []
    for line in path.read_text(encoding='utf-8').splitlines():
        m = header.match(line)
        if m:
            if cur_s is not None:
                chunks.append((cur_s, cur_e, '\n'.join(cur_lines).strip()))
            cur_s, cur_e, cur_lines = float(m.group(1)), float(m.group(2)), []
        elif cur_s is not None:
            cur_lines.append(line)
    if cur_s is not None:
        chunks.append((cur_s, cur_e, '\n'.join(cur_lines).strip()))
    return chunks


def write_postprocessed(out_path: Path,
                         chunks: list[tuple[float, float, str]]) -> None:
    lines = []
    for i, (s, e, text) in enumerate(chunks, 1):
        lines.append(f'=== Chunk {i} [{s:.2f}s - {e:.2f}s] ===')
        lines.append(text)
        lines.append('')
    out_path.write_text('\n'.join(lines), encoding='utf-8')


def best_source(title: str, prefer: str) -> Path | None:
    """Return the best existing transcription file for this title."""
    candidates = []
    if prefer == 'merged':
        candidates = [
            TRANSCRIPTIONS / f'{title}_merged.txt',
            TRANSCRIPTIONS / f'{title}_combined.txt',
        ]
    else:
        candidates = [
            TRANSCRIPTIONS / f'{title}_combined.txt',
            TRANSCRIPTIONS / f'{title}_merged.txt',
        ]
    for p in candidates:
        if p.exists():
            return p
    return None


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--filter',        default='',          help='Title substring filter')
    parser.add_argument('--skip-existing', action='store_true', help='Skip if _postprocessed.txt exists')
    parser.add_argument('--source',        default='combined',  choices=['combined', 'merged'],
                        help='Prefer _combined.txt or _merged.txt as input')
    parser.add_argument('--dry-run',       action='store_true')
    args = parser.parse_args()

    # Collect titles from all _combined.txt files
    all_files = sorted(TRANSCRIPTIONS.glob('*_combined.txt'))
    if args.filter:
        all_files = [f for f in all_files if args.filter in f.name]

    # Derive titles (strip _combined.txt suffix)
    titles = [f.stem[:-len('_combined')] for f in all_files]
    print(f'Found {len(titles)} transcription(s) matching filter "{args.filter}"')

    if args.dry_run:
        for t in titles:
            src = best_source(t, args.source)
            out = TRANSCRIPTIONS / f'{t}_postprocessed.txt'
            exists = '✓' if out.exists() else '✗'
            src_label = src.name if src else 'MISSING'
            print(f'  [{exists}] {t[:70]}  (src: {src_label})')
        return

    print('Loading LLM...')
    llm = get_llm()
    print(f'  → {type(llm).__name__}\n')

    ok = fail = skip = 0
    for i, title in enumerate(titles, 1):
        out_path = TRANSCRIPTIONS / f'{title}_postprocessed.txt'

        if args.skip_existing and out_path.exists():
            print(f'[{i}/{len(titles)}] SKIP {title[:65]}')
            skip += 1
            continue

        src = best_source(title, args.source)
        if src is None:
            print(f'[{i}/{len(titles)}] MISSING source for {title[:65]}')
            fail += 1
            continue

        print(f'[{i}/{len(titles)}] {title[:65]}')
        print(f'  Source: {src.name}')

        try:
            chunks = parse_chunks(src)
            cleaned = []
            for ci, (s, e, text) in enumerate(chunks, 1):
                result = llm_clean_chunk(llm, text)
                cleaned.append((s, e, result))
                print(f'  Chunk {ci}/{len(chunks)}: {result[:70]}')

            write_postprocessed(out_path, cleaned)
            print(f'  Saved → {out_path.name}')
            ok += 1
        except Exception as e:
            print(f'  ERROR: {e}')
            fail += 1

    print(f'\nDone. OK: {ok}, Skipped: {skip}, Failed: {fail}')


if __name__ == '__main__':
    main()
