import hashlib
import json
import re
import sqlite3
import unicodedata
from contextlib import closing

from ..config import DATA_DIR, QUESTION_BANK_PATH


CACHEABLE_TYPES = {"SingleChoice", "MultipleChoice", "Judgement"}
DATABASE_PATH = QUESTION_BANK_PATH
SEED_PATH = DATA_DIR / "question_bank_seed.json"
SEED_VERSION = "1"


def _normalize(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def _question_key(question):
    question_type = question.get("Type")
    if question_type not in CACHEABLE_TYPES:
        return None
    body = question.get("Body")
    options = question.get("Options")
    if not isinstance(body, str) or not isinstance(options, list):
        return None
    if not options or not all(isinstance(option, str) for option in options):
        return None
    normalized = {
        "type": question_type,
        "body": _normalize(body),
        "options": [_normalize(option) for option in options],
    }
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class QuestionBank:
    def __init__(self, path=DATABASE_PATH):
        self.path = path
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute(
                """CREATE TABLE IF NOT EXISTS answers (
                    question_key TEXT PRIMARY KEY,
                    question_type TEXT NOT NULL,
                    body TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    answer_json TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    source TEXT NOT NULL,
                    valid INTEGER NOT NULL DEFAULT 1
                )"""
            )
            seeded = db.execute("SELECT value FROM metadata WHERE key = 'seed_version'").fetchone()
            if seeded is None or seeded[0] != SEED_VERSION:
                with SEED_PATH.open(encoding="utf-8") as seed_file:
                    seed_entries = json.load(seed_file)
                for entry in seed_entries:
                    question = entry["question"]
                    key = _question_key(question)
                    if key is None:
                        continue
                    db.execute(
                        """INSERT OR IGNORE INTO answers
                        (question_key, question_type, body, options_json,
                         answer_json, explanation, source)
                        VALUES (?, ?, ?, ?, ?, ?, 'seed')""",
                        (
                            key,
                            question["Type"],
                            question["Body"],
                            json.dumps(question["Options"], ensure_ascii=False),
                            json.dumps(entry["answer"], ensure_ascii=False),
                            entry["explanation"],
                        ),
                    )
                db.execute(
                    "INSERT INTO metadata (key, value) VALUES ('seed_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (SEED_VERSION,),
                )

    def lookup(self, question):
        key = _question_key(question)
        if key is None:
            return None
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute(
                "SELECT answer_json, explanation FROM answers WHERE question_key = ? AND valid = 1",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0]), row[1]

    def save_verified(self, question, answer, explanation=""):
        key = _question_key(question)
        if key is None:
            return
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                """INSERT INTO answers
                (question_key, question_type, body, options_json,
                 answer_json, explanation, source, valid)
                VALUES (?, ?, ?, ?, ?, ?, 'verified', 1)
                ON CONFLICT(question_key) DO UPDATE SET
                    answer_json = excluded.answer_json,
                    explanation = CASE WHEN excluded.explanation <> ''
                        THEN excluded.explanation ELSE answers.explanation END,
                    source = 'verified',
                    valid = 1""",
                (
                    key,
                    question["Type"],
                    question["Body"],
                    json.dumps(question["Options"], ensure_ascii=False),
                    json.dumps(answer, ensure_ascii=False),
                    explanation,
                ),
            )

    def invalidate(self, question):
        key = _question_key(question)
        if key is None:
            return
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "UPDATE answers SET valid = 0 WHERE question_key = ?", (key,)
            )
