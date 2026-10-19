from __future__ import annotations
from datetime import date
from typing import Tuple, Optional
import re

def parse_fact_line(line: str) -> Tuple[date, str]:
    """
    Parse a line from MEMORY.md in the format '- (YYYY-MM-DD) fact text' and return a tuple
    of (datetime.date, str) with the fact text stripped. If the line is invalid, raise ValueError.
    """
    # Regular expression to match the line format
    pattern = r'^- \((\d{4}-\d{2}-\d{2})\) (.*)$'
    match = re.match(pattern, line)
    
    if not match:
        raise ValueError("Line does not match the required format '- (YYYY-MM-DD) fact text'")
    
    date_str, fact_text = match.groups()
    
    try:
        fact_date = date.fromisoformat(date_str)
    except ValueError:
        raise ValueError("Date is not a valid calendar date")
    
    return (fact_date, fact_text.strip())

# Tests for parse_fact_line
def test_parse_fact_line_valid():
    line = "- (2026-10-10) Temperatures should be given in degrees Fahrenheit for this user."
    result = parse_fact_line(line)
    assert result[0] == date(2026, 10, 10)
    assert result[1] == "Temperatures should be given in degrees Fahrenheit for this user."

def test_parse_fact_line_invalid_date():
    line = "- (2026-13-10) Invalid date"
    try:
        parse_fact_line(line)
    except ValueError as e:
        assert str(e) == "Date is not a valid calendar date"

def test_parse_fact_line_invalid_format():
    line = "Invalid format line"
    try:
        parse_fact_line(line)
    except ValueError as e:
        assert str(e) == "Line does not match the required format '- (YYYY-MM-DD) fact text'"

def test_parse_fact_line_extra_spaces():
    line = "- (2026-10-10)   Extra spaces in fact text   "
    result = parse_fact_line(line)
    assert result[0] == date(2026, 10, 10)
    assert result[1] == "Extra spaces in fact text"

def test_parse_fact_line_empty_fact_text():
    line = "- (2026-10-10) "
    result = parse_fact_line(line)
    assert result[0] == date(2026, 10, 10)
    assert result[1] == ""
