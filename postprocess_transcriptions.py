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


try:
    from asr_keywords import MISHEARD
except Exception:
    MISHEARD = {}


def cheap_clean(text: str) -> str:
    """Rule-based pre-clean before hitting the LLM (saves tokens, reduces noise)."""
    # Collapse runs of the same CJK char → max 2
    text = _REP_CJK.sub(lambda m: m.group(1) * 2, text)
    # Collapse 那個那個那個… → 那個那個
    text = _REP_NAGE.sub('那個那個', text)
    # Strip stray ASCII error messages that slipped through
    text = re.sub(r'\[Error in chunk \d+:.*?\]', '', text, flags=re.DOTALL)
    # Deterministic member-name mishear fixes (e.g. 巴毛 → 八毛) — more reliable than
    # relying on the LLM. Safe because these tokens aren't real words otherwise.
    for wrong, right in MISHEARD.items():
        text = text.replace(wrong, right)
    return text.strip()


# ── LLM setup ─────────────────────────────────────────────────────────────────

class _Resp:
    """Minimal stand-in for a LangChain message so callers can read .content."""
    __slots__ = ('content',)
    def __init__(self, content: str):
        self.content = content


class TransformersChat:
    """Local HF text-generation model with a .invoke(messages) → _Resp interface,
    matching how the rest of this script calls the LLM.

    Default model: Taiwan-LLM-7B-v2.0-chat (yentinglin) — best Taiwanese Mandarin,
    ships only safetensors (no GGUF), so it's run via transformers rather than
    Ollama. The pipeline is loaded lazily on first invoke and reused.
    """
    def __init__(self, model_id: str):
        self.model_id = model_id
        self._pipe = None

    def _ensure(self):
        if self._pipe is not None:
            return
        import torch
        from transformers import pipeline
        print(f'  Loading {self.model_id} via transformers (first call is slow)...')
        use_cuda = torch.cuda.is_available()
        # Use `device=` (not `device_map='auto'`) so we don't hard-require accelerate;
        # a 7B model fits a single GPU. `dtype` (torch_dtype is deprecated in 4.5x).
        self._pipe = pipeline(
            'text-generation',
            model=self.model_id,
            dtype=torch.bfloat16 if use_cuda else torch.float32,
            device=0 if use_cuda else -1,
        )

    def invoke(self, messages):
        self._ensure()
        tok = self._pipe.tokenizer
        prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        out = self._pipe(
            prompt,
            # Chunks are <=30s of speech (~a few hundred tokens). Cap kept modest so a
            # looping/hallucinating generation can't pad the output with redundant fill.
            max_new_tokens=int(os.getenv('ASR_CLEAN_MAX_NEW_TOKENS', '512')),
            do_sample=False,           # deterministic cleanup, not creative generation
            return_full_text=False,    # only the newly generated text, not the prompt
        )
        return _Resp(out[0]['generated_text'].strip())


def get_llm():
    # ASR cleanup backend. Taiwan-LLM ships safetensors only, so the default path is
    # transformers. Set ASR_CLEAN_BACKEND=ollama|openai to override.
    # NOTE: intentionally does NOT inherit NL_QUERY_LLM — that's the RAG query
    # backend (often ollama on a non-loopback host), which is unrelated to and
    # would hijack ASR cleanup.
    backend = os.getenv('ASR_CLEAN_BACKEND', 'transformers').strip().lower()
    if backend == 'transformers':
        return TransformersChat(os.getenv('ASR_CLEAN_MODEL',
                                          'yentinglin/Taiwan-LLM-7B-v2.0-chat'))
    if backend == 'ollama':
        from langchain_ollama import ChatOllama
        mdl = os.getenv('OLLAMA_ASR_CLEAN_MODEL') or os.getenv('OLLAMA_NL_MODEL', 'llama3.2')
        kwargs = dict(model=mdl, temperature=0.1,
                      timeout=int(os.getenv('OLLAMA_TIMEOUT', '120')),
                      num_ctx=int(os.getenv('OLLAMA_ASR_NUM_CTX', '4096')))
        base_url = os.getenv('OLLAMA_BASE_URL')
        if base_url:
            kwargs['base_url'] = base_url
        return ChatOllama(**kwargs)
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=os.getenv('OPENAI_NL_MODEL', 'gpt-4o-mini'), temperature=0.1)


SYSTEM_PROMPT = """\
你是LNG Gaming頻道直播字幕的後製專家。
固定成員（6位，幾乎每次都出現）：小六、六探、鳥屎、Leggy、八毛、老王。
偶爾出現的名字：展邱、奶哥、悅悅、顏顏、蕾蕾、探探、天神。
常見誤聽修正：「巴毛」應為「八毛」。
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


# ── Self-consistency reconciliation (#4) ────────────────────────────────────────
# When ASR ran with ASR_SELF_CONSISTENCY=1 it emits two candidates per uncertain
# chunk (beam + greedy). Where they disagree, one usually has the right word. The
# LLM picks/merges the correct reading using channel context, then cleans as usual.

RECONCILE_TEMPLATE = (
    "同一段語音有兩種ASR辨識結果，可能在人名、遊戲名或用詞上不同。\n"
    "請依上下文與頻道背景，判斷哪個較正確，融合成一個最正確的版本，"
    "並套用上述清理規則（修正名稱、加標點、保留語氣）。\n\n"
    "版本A（beam）：\n{a}\n\n版本B（greedy）：\n{b}\n\n最正確且清理後的版本："
)


def llm_reconcile_chunk(llm, beam: str, greedy: str) -> str:
    """Reconcile two ASR candidates into one corrected, cleaned reading."""
    beam_c, greedy_c = cheap_clean(beam), cheap_clean(greedy)
    if not beam_c and not greedy_c:
        return ''
    if not greedy_c or beam_c == greedy_c:
        return llm_clean_chunk(llm, beam_c or greedy_c)
    prompt = RECONCILE_TEMPLATE.format(a=beam_c[:1500], b=greedy_c[:1500])
    try:
        resp = llm.invoke([
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user',   'content': prompt},
        ])
        result = re.sub(r'<think>.*?</think>', '', resp.content, flags=re.DOTALL).strip()
        return result or beam_c
    except Exception as e:
        print(f'    LLM reconcile error: {e} — keeping beam candidate')
        return llm_clean_chunk(llm, beam_c)


def parse_candidates(path: Path) -> dict[int, tuple[str, str]]:
    """Parse a <title>_candidates.txt sidecar → {chunk_index: (beam, greedy)}.
    chunk_index is 1-based to match the '=== Chunk N ===' headers in _combined.txt.
    """
    if not path.exists():
        return {}
    header = re.compile(r'=== Chunk (\d+) \[')
    out: dict[int, tuple[str, str]] = {}
    idx, which, beam_lines, greedy_lines = None, None, [], []

    def _flush():
        if idx is not None:
            out[idx] = ('\n'.join(beam_lines).strip(), '\n'.join(greedy_lines).strip())

    for line in path.read_text(encoding='utf-8').splitlines():
        m = header.match(line)
        if m:
            _flush()
            idx, which, beam_lines, greedy_lines = int(m.group(1)), None, [], []
        elif line.strip() == '<<BEAM>>':
            which = 'beam'
        elif line.strip() == '<<GREEDY>>':
            which = 'greedy'
        elif idx is not None and which == 'beam':
            beam_lines.append(line)
        elif idx is not None and which == 'greedy':
            greedy_lines.append(line)
    _flush()
    return out


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
    parser.add_argument('--use-candidates', action='store_true',
                        help='If a <title>_candidates.txt sidecar exists (from ASR '
                             'self-consistency), reconcile beam+greedy per chunk')
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
            candidates = {}
            if args.use_candidates:
                candidates = parse_candidates(TRANSCRIPTIONS / f'{title}_candidates.txt')
                if candidates:
                    print(f'  Candidates sidecar: {len(candidates)} chunk(s) to reconcile')
            cleaned = []
            for ci, (s, e, text) in enumerate(chunks, 1):
                if ci in candidates:
                    beam, greedy = candidates[ci]
                    result = llm_reconcile_chunk(llm, beam or text, greedy)
                else:
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
