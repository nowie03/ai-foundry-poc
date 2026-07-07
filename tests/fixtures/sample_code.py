# fixtures/sample_code.py
# Used by skills.yaml → code-review suite.
# Intentionally contains several issues for the agent to find.

import os
import sqlite3


SECRET_KEY = "hardcoded-secret-12345"          # [ISSUE] hardcoded secret


def get_user(username: str) -> dict | None:
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    # [ISSUE] SQL injection — username is interpolated directly
    cur.execute(f"SELECT * FROM users WHERE username = '{username}'")
    row = cur.fetchone()
    conn.close()
    return {"username": row[0], "email": row[1]} if row else None


def process_items(items):
    result = []
    for i in range(len(items)):          # [STYLE] use enumerate or direct iteration
        result.append(items[i] * 2)
    return result


def load_config(path: str) -> dict:
    # [ISSUE] no error handling if file doesn't exist
    with open(path) as f:
        import json
        return json.load(f)


def divide(a, b):
    # [ISSUE] no guard against ZeroDivisionError
    return a / b
