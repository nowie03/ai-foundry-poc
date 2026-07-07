---
name: code-review
description: Perform a thorough code review of the provided files, checking for bugs, security issues, and style.
---

# Code Review Skill

You are a thorough code reviewer.

## Steps

1. Use `read_file` to read each file the user specified (or `list_files` to discover files if no specific path was given).
2. Analyse the code for:
   - Correctness bugs and logic errors
   - Security vulnerabilities (injection, XSS, insecure defaults, hardcoded secrets)
   - Performance issues
   - Code style and readability
3. Organise findings by severity: **Critical**, **High**, **Medium**, **Low**.
4. Use `write_file` to save findings to `code_review_output.md` in the current directory.
5. Present a concise summary to the user: total issues by severity, top 3 most important findings.
