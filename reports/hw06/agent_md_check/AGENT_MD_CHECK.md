# AGENT.md compliance of a generated function

Generated 2026-10-16 12:34 by `make agent-md-check-hw06` (qwen3:8b, system prompt = AGENT.md + MEMORY.md).

Task given to the model (it does not restate the conventions):

> Write a new Python module for this repository containing a function `parse_fact_line(line)` that parses one MEMORY.md bullet of the form '- (YYYY-MM-DD) fact text' and returns a tuple of (datetime.date, str) with the fact text stripped. Lines that do not match this form, or whose date is not a real calendar date, are invalid input. Include the module's tests in the same file. Reply with only the complete module in a single ```python code block.

**11/12 checkable AGENT.md rules followed; behaviour tests: FAIL.**

| Category | AGENT.md rule | Result |
|---|---|---|
| Coding conventions | Every module starts with a docstring | FAIL |
| Coding conventions | ... and `from __future__ import annotations` | PASS |
| Coding conventions | Type hints on all parameters and on the return value | PASS |
| Coding conventions | Every function has a docstring | PASS |
| Coding conventions | snake_case function names, UPPER_CASE constants | PASS |
| Coding conventions | Invalid input raises a specific exception; no bare `except:` | PASS |
| Coding conventions | Never return None to signal an error | PASS |
| Coding conventions | Library code does not print | PASS |
| Testing approach | Tests are plain test_* functions using assert, valid + invalid case | PASS |
| Testing approach | Tests run offline (no network/DB/Ollama imports) | PASS |
| Prohibited actions | Never use eval or exec | PASS |
| Project description | Never hard-code 8817 or s7117 | PASS |

## Behaviour (run with `python -I` in a subprocess)

| Test | Result |
|---|---|
| valid_line | pass |
| strips_whitespace | fail: ValueError: Line does not match the required format '- (YYYY-MM-DD) fact text' |
| invalid_format_raises_ValueError | pass |
| invalid_date_raises_ValueError | pass |
| generated_test_names | ['test_parse_fact_line_empty_fact_text', 'test_parse_fact_line_extra_spaces', 'test_parse_fact_line_invalid_date', 'test_parse_fact_line_invalid_format', 'test_parse_fact_line_valid'] |
| generated_tests_pass | pass |
