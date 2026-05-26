"""
Quiz/test system DB operations — backed by SQLite (lng_graphrag.db).
Tables: questions, user_question_stats, question_attempts
"""
import json
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any

DB_PATH = Path(__file__).parent / "lng_graphrag.db"

QUESTION_TYPES = ('facts', 'content')
DIFFICULTIES = ('easy', 'hard')
STATUSES = ('active', 'pending', 'rejected')


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_quiz_tables() -> None:
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS questions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                type          TEXT NOT NULL CHECK(type IN ('facts','content')),
                difficulty    TEXT NOT NULL CHECK(difficulty IN ('easy','hard')),
                question_text TEXT NOT NULL,
                options       TEXT NOT NULL,
                correct_answer TEXT NOT NULL,
                explanation   TEXT,
                source_doc    TEXT,
                source_chunk  INTEGER,
                status        TEXT NOT NULL DEFAULT 'pending'
                              CHECK(status IN ('active','pending','rejected')),
                created_by    INTEGER,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_q_type_diff_status
                ON questions(type, difficulty, status);

            CREATE TABLE IF NOT EXISTS user_question_stats (
                user_id       INTEGER NOT NULL,
                question_id   INTEGER NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                last_answered DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, question_id)
            );
            CREATE INDEX IF NOT EXISTS idx_uqs_question
                ON user_question_stats(question_id);

            CREATE TABLE IF NOT EXISTS question_attempts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                is_correct  INTEGER NOT NULL,
                answered_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_qa_user_q
                ON question_attempts(user_id, question_id);
            CREATE INDEX IF NOT EXISTS idx_qa_question
                ON question_attempts(question_id);
        """)


def _row_to_dict(row) -> Dict:
    if row is None:
        return None
    d = dict(row)
    if isinstance(d.get('options'), str):
        try:
            d['options'] = json.loads(d['options'])
        except Exception:
            pass
    return d


def get_questions(
    qtype: str,
    difficulty: str,
    mode: str,
    count: int,
    user_id: Optional[int] = None,
    skip_answered: bool = True,
) -> List[Dict]:
    if qtype not in QUESTION_TYPES or difficulty not in DIFFICULTIES:
        return []
    count = min(max(count, 1), 100)

    with _connect() as conn:
        if mode == 'hard':
            rows = conn.execute("""
                SELECT q.id, q.type, q.difficulty, q.question_text, q.options,
                       q.correct_answer, q.explanation,
                       COALESCE(gs.error_rate, 0.5) AS error_rate
                FROM questions q
                LEFT JOIN (
                    SELECT question_id,
                           1.0 - CAST(SUM(correct_count) AS REAL)
                               / NULLIF(SUM(attempt_count), 0) AS error_rate
                    FROM user_question_stats
                    GROUP BY question_id
                    HAVING SUM(attempt_count) >= 3
                ) gs ON q.id = gs.question_id
                WHERE q.type = ? AND q.difficulty = ? AND q.status = 'active'
                ORDER BY error_rate DESC, RANDOM()
                LIMIT ?
            """, (qtype, difficulty, count)).fetchall()
        elif user_id and skip_answered:
            rows = conn.execute("""
                SELECT q.id, q.type, q.difficulty, q.question_text, q.options,
                       q.correct_answer, q.explanation
                FROM questions q
                LEFT JOIN user_question_stats uqs
                    ON q.id = uqs.question_id AND uqs.user_id = ?
                WHERE q.type = ? AND q.difficulty = ? AND q.status = 'active'
                  AND uqs.question_id IS NULL
                ORDER BY RANDOM()
                LIMIT ?
            """, (user_id, qtype, difficulty, count)).fetchall()
        else:
            rows = conn.execute("""
                SELECT q.id, q.type, q.difficulty, q.question_text, q.options,
                       q.correct_answer, q.explanation
                FROM questions q
                WHERE q.type = ? AND q.difficulty = ? AND q.status = 'active'
                ORDER BY RANDOM()
                LIMIT ?
            """, (qtype, difficulty, count)).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_question_by_id(question_id: int) -> Optional[Dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM questions WHERE id = ? AND status = 'active'",
            (question_id,)
        ).fetchone()
        return _row_to_dict(row)


def record_attempt(user_id: int, question_id: int, is_correct: bool) -> None:
    correct_int = 1 if is_correct else 0
    with _connect() as conn:
        conn.execute(
            "INSERT INTO question_attempts (user_id, question_id, is_correct) VALUES (?,?,?)",
            (user_id, question_id, correct_int)
        )
        conn.execute("""
            INSERT INTO user_question_stats (user_id, question_id, attempt_count, correct_count, last_answered)
            VALUES (?, ?, 1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, question_id) DO UPDATE SET
                attempt_count = attempt_count + 1,
                correct_count = correct_count + excluded.correct_count,
                last_answered = CURRENT_TIMESTAMP
        """, (user_id, question_id, correct_int))
        conn.commit()


def get_user_quiz_stats(user_id: int) -> Dict:
    with _connect() as conn:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(attempt_count), 0)  AS total_attempts,
                COALESCE(SUM(correct_count), 0)  AS total_correct,
                COUNT(DISTINCT question_id)       AS questions_attempted
            FROM user_question_stats WHERE user_id = ?
        """, (user_id,)).fetchone()
        totals = dict(row) if row else {}

        breakdown_rows = conn.execute("""
            SELECT q.type, q.difficulty,
                   SUM(s.attempt_count) AS attempts,
                   SUM(s.correct_count) AS correct
            FROM user_question_stats s
            JOIN questions q ON s.question_id = q.id
            WHERE s.user_id = ?
            GROUP BY q.type, q.difficulty
        """, (user_id,)).fetchall()

        breakdown = {}
        for r in breakdown_rows:
            key = f"{r['type']}_{r['difficulty']}"
            breakdown[key] = {
                'attempts': int(r['attempts'] or 0),
                'correct':  int(r['correct'] or 0),
            }
        return {
            'total_attempts':      int(totals.get('total_attempts') or 0),
            'total_correct':       int(totals.get('total_correct') or 0),
            'questions_attempted': int(totals.get('questions_attempted') or 0),
            'breakdown':           breakdown,
        }


def count_by_source(source_doc: str, qtype: str, difficulty: str) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM questions WHERE source_doc=? AND type=? AND difficulty=? AND status='active'",
            (source_doc, qtype, difficulty)
        ).fetchone()
        return row[0] if row else 0


def count_active_questions() -> Dict[str, int]:
    with _connect() as conn:
        rows = conn.execute("""
            SELECT type, difficulty, COUNT(*) AS cnt
            FROM questions WHERE status = 'active'
            GROUP BY type, difficulty
        """).fetchall()
        return {f"{r['type']}_{r['difficulty']}": int(r['cnt']) for r in rows}


def add_question(
    qtype: str,
    difficulty: str,
    question_text: str,
    options: List[str],
    correct_answer: str,
    explanation: Optional[str] = None,
    source_doc: Optional[str] = None,
    source_chunk: Optional[int] = None,
    created_by: Optional[int] = None,
    status: str = 'pending',
) -> Optional[int]:
    try:
        with _connect() as conn:
            cur = conn.execute("""
                INSERT INTO questions
                    (type, difficulty, question_text, options, correct_answer,
                     explanation, source_doc, source_chunk, created_by, status)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                qtype, difficulty, question_text,
                json.dumps(options, ensure_ascii=False),
                correct_answer, explanation or None,
                source_doc or None, source_chunk,
                created_by, status,
            ))
            conn.commit()
            return cur.lastrowid
    except Exception:
        return None


def get_pending_questions(limit: int = 50) -> List[Dict]:
    with _connect() as conn:
        rows = conn.execute("""
            SELECT id, type, difficulty, question_text, options,
                   correct_answer, explanation, source_doc,
                   created_at, created_by
            FROM questions
            WHERE status = 'pending'
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [_row_to_dict(r) for r in rows]


def update_question_status(question_id: int, status: str) -> bool:
    if status not in STATUSES:
        return False
    try:
        with _connect() as conn:
            conn.execute("UPDATE questions SET status=? WHERE id=?", (status, question_id))
            conn.commit()
        return True
    except Exception:
        return False
