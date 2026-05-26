"""
generate_quiz_questions.py — Populate quiz question bank from transcriptions using LLM.

Usage:
    python generate_quiz_questions.py                          # all types, all difficulties
    python generate_quiz_questions.py --type facts --difficulty easy
    python generate_quiz_questions.py --max-files 3 --per-chunk 2
    python generate_quiz_questions.py --dry-run                # preview without writing to DB
"""
import os
import sys
import json
import re
import argparse
from pathlib import Path

# Force UTF-8 output so filenames with special chars don't crash on Windows cp950
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TRANSCRIPTIONS_DIR = Path("./transcriptions")

PROMPTS = {
    ('facts', 'easy'): """\
你是一個中文出題老師。根據以下逐字稿片段，出 {n} 道是非題。
規則：
- 每題測試對話中的具體事實，答案是「正確」或「錯誤」
- 避免模糊主觀的題目
- explanation 用一句話解釋理由
- 只回覆 JSON，不要其他文字

逐字稿：
{text}

格式（JSON array）：
[{{"question_text":"...","options":["正確","錯誤"],"correct_answer":"正確","explanation":"..."}}]""",

    ('facts', 'hard'): """\
你是一個中文出題老師。根據以下逐字稿，出 1 道四選一選擇題，測試對話中的具體細節。
規則：
- 選一個具體事實（數字、名稱、時間、地點）出題
- 4 個選項只有 1 個正確，其餘 3 個要有迷惑性
- explanation 說明正確答案依據
- 只回覆 JSON，不要其他文字

逐字稿：
{text}

格式（JSON array）：
[{{"question_text":"...","options":["A","B","C","D"],"correct_answer":"A","explanation":"..."}}]""",

    ('content', 'easy'): """\
你是一個中文出題老師。根據以下逐字稿，出 {n} 道理解性四選一選擇題，測試對話主題與意涵。
規則：
- 測試段落主旨、人物意圖、對話氛圍
- 4 個選項只有 1 個最正確
- explanation 解釋為何此答案最佳
- 只回覆 JSON，不要其他文字

逐字稿：
{text}

格式（JSON array）：
[{{"question_text":"...","options":["A","B","C","D"],"correct_answer":"A","explanation":"..."}}]""",

    ('content', 'hard'): """\
你是一個中文出題老師。從以下逐字稿找出 1 個最特別、最值得記住的關鍵詞（人名、地名、數字、專有名詞優先），做成 1 道克漏字選擇題。
規則：
- 從原文抽取一個短句，把關鍵詞換成「___」
- 4 個選項：1 個正確答案 + 3 個容易混淆的錯誤選項
- 答案必須在選項中
- 只回覆 JSON，不要其他文字

逐字稿：
{text}

格式（JSON array，只要 1 題）：
[{{"question_text":"他去了___拍攝","options":["台北","台南","高雄","花蓮"],"correct_answer":"台南","explanation":"原文提到他去台南拍攝"}}]""",
}


def get_llm():
    backend = os.getenv("NL_QUERY_LLM", "openai").strip().lower()
    if backend == "ollama":
        from langchain_ollama import ChatOllama
        model = os.getenv("OLLAMA_NL_MODEL", "llama3.2")
        timeout = int(os.getenv("OLLAMA_TIMEOUT", "120"))
        num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
        return ChatOllama(model=model, temperature=0.7, timeout=timeout, num_ctx=num_ctx)
    else:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=os.getenv("OPENAI_NL_MODEL", "gpt-4o-mini"), temperature=0.7)


def _no_think(prompt: str) -> str:
    """Append /no_think for Qwen3 models to skip CoT output."""
    model = os.getenv("OLLAMA_NL_MODEL", "")
    if "qwen3" in model.lower() or "qwen3.5" in model.lower():
        return prompt + "\n/no_think"
    return prompt


def parse_llm_json(text: str) -> list:
    text = text.strip()
    # Strip Qwen3-style <think>...</think> blocks
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    # Strip markdown code fences
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```\s*$', '', text)
    # Try outermost JSON array first
    start = text.find('[')
    if start != -1:
        depth, i = 0, start
        for i, ch in enumerate(text[start:], start):
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    break
        try:
            return json.loads(text[start:i + 1])
        except json.JSONDecodeError:
            pass
    # Fall back: single JSON object — wrap in list
    start = text.find('{')
    if start != -1:
        depth, i = 0, start
        for i, ch in enumerate(text[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    break
        try:
            obj = json.loads(text[start:i + 1])
            return [obj] if isinstance(obj, dict) else []
        except json.JSONDecodeError:
            pass
    return []


_JUNK_PATTERNS = ('CUDA', 'Traceback', 'Exception', 'Error:', 'assert', 'LAUNCH_BLOCKING',
                  'RuntimeError', 'ImportError', 'stderr')

def _looks_like_error(s: str) -> bool:
    return any(p in s for p in _JUNK_PATTERNS)


def validate_questions(raw: list, qtype: str) -> list:
    valid = []
    for q in raw:
        if not isinstance(q, dict):
            continue
        text = (q.get('question_text') or '').strip()
        opts = q.get('options')
        ans = (q.get('correct_answer') or '').strip()
        if not text or not isinstance(opts, list) or len(opts) < 2 or not ans:
            continue
        if _looks_like_error(text) or _looks_like_error(ans) or any(_looks_like_error(str(o)) for o in opts):
            continue
        if ans not in opts:
            continue
        valid.append({
            'question_text': text,
            'options': [str(o).strip() for o in opts],
            'correct_answer': ans,
            'explanation': (q.get('explanation') or '').strip(),
        })
    return valid


def load_chunks(filepath: Path) -> list:
    chunks, current = [], []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if re.match(r'^=== Chunk \d+', line):
                text = ' '.join(current).strip()
                if len(text) > 80:
                    chunks.append(text)
                current = []
            else:
                stripped = line.strip()
                if stripped:
                    current.append(stripped)
    if current:
        text = ' '.join(current).strip()
        if len(text) > 80:
            chunks.append(text)
    return chunks


def main():
    parser = argparse.ArgumentParser(description="Generate quiz questions from transcriptions")
    parser.add_argument('--type', choices=['facts', 'content', 'all'], default='all')
    parser.add_argument('--difficulty', choices=['easy', 'hard', 'all'], default='all')
    parser.add_argument('--per-chunk', type=int, default=2, help='Questions per chunk')
    parser.add_argument('--max-files', type=int, default=None)
    parser.add_argument('--max-chunks', type=int, default=10, help='Max chunks per file (default 10)')
    parser.add_argument('--dry-run', action='store_true', help='Print questions without writing to DB')
    parser.add_argument('--skip-existing', action='store_true', help='Skip files already in DB for the given type/difficulty')
    parser.add_argument('--filter', dest='filter_str', default=None, help='Only process files whose name contains this substring')
    args = parser.parse_args()

    import quiz_db
    if not args.dry_run:
        quiz_db.init_quiz_tables()

    types = ['facts', 'content'] if args.type == 'all' else [args.type]
    difficulties = ['easy', 'hard'] if args.difficulty == 'all' else [args.difficulty]

    files = sorted(TRANSCRIPTIONS_DIR.glob('*_combined.txt'))
    if args.filter_str:
        files = [f for f in files if args.filter_str in f.name]
    if args.max_files:
        files = files[:args.max_files]
    if not files:
        print("No transcription files found in ./transcriptions/")
        return

    print(f"Files: {len(files)}  |  Types: {types}  |  Difficulties: {difficulties}")
    llm = get_llm()
    total_added = 0

    for filepath in files:
        source_doc = filepath.name
        print(f"\n{source_doc}")
        chunks = load_chunks(filepath)
        if args.max_chunks:
            chunks = chunks[:args.max_chunks]
        print(f"  {len(chunks)} chunks")

        for qtype in types:
            for diff in difficulties:
                key = (qtype, diff)
                prompt_tpl = PROMPTS.get(key)
                if not prompt_tpl:
                    continue
                if args.skip_existing and not args.dry_run:
                    already = quiz_db.count_by_source(source_doc, qtype, diff)
                    if already > 0:
                        print(f"  [{qtype}/{diff}] skipped (already {already} questions)")
                        continue
                added = 0
                for chunk_idx, chunk_text in enumerate(chunks):
                    prompt = prompt_tpl.format(n=args.per_chunk, text=chunk_text[:2500])
                    try:
                        resp = llm.invoke([{"role": "user", "content": prompt}])
                        raw = parse_llm_json(resp.content)
                        questions = validate_questions(raw, qtype)
                    except Exception as e:
                        print(f"  LLM error (chunk {chunk_idx}): {e}")
                        continue

                    for q in questions:
                        if args.dry_run:
                            print(f"  [DRY] [{qtype}/{diff}] {q['question_text'][:60]}...")
                            total_added += 1
                        else:
                            qid = quiz_db.add_question(
                                qtype=qtype, difficulty=diff,
                                question_text=q['question_text'],
                                options=q['options'],
                                correct_answer=q['correct_answer'],
                                explanation=q['explanation'],
                                source_doc=source_doc,
                                source_chunk=chunk_idx,
                                created_by=None,
                                status='active',
                            )
                            if qid:
                                added += 1
                                total_added += 1

                if not args.dry_run:
                    print(f"  [{qtype}/{diff}] +{added} questions")

    print(f"\nTotal {'previewed' if args.dry_run else 'added'}: {total_added}")


if __name__ == '__main__':
    main()
