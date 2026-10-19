# MEMORY.md
<!-- last_consolidated: 2026-10-16T19:16:51+00:00 -->
<!-- Durable facts. Consolidated by code/file_memory/consolidation.py; [Fxx] = source lines of the version before consolidation. -->

## Facts
- (2026-09-01) The user covers the Downtown San Jose district. [F03]
- (2026-09-02) The user's supervisor is Mark Chen. [F04]
- (2026-09-10) The user prefers reports written as numbered paragraphs. [F12]
- (2026-09-15) The local model is qwen3:8b served by Ollama. [F11+F17]
- (2026-09-16) The user is a senior environmental health inspector with Santa Clara County. [F01+F02+F06+F15+F18]
- (2026-09-16) Rachandeep Kaur works as a senior inspector for Santa Clara County. [F01+F06+F15+F18]
- (2026-09-17) Yummy Kitchen's facility code is FA0206933. [F13+F19]
- (2026-09-20) Golden Dragon's facility code is FA0148210 (confirmed from the county permit). [F20]
- (2026-09-23) The user starts field inspections at 8 AM on weekdays. [F09+F22]
- (2026-09-26) The relational database is s7117_rel on MySQL. [F08+F24]
- (2026-09-26) MySQL database s7117_rel holds the relational inspection data. [F24]
- (2026-09-27) Closure recommendations must be escalated to the user's supervisor. [F25]
- (2026-10-02) Golden Dragon failed the cold-holding check with its walk-in cooler at 47F. [F21+F29]
- (2026-10-06) Sakura Sushi must log rice pH every 4 hours. [F26+F33]
- (2026-10-08) The user prefers short answers of at most four sentences. [F35]
- (2026-10-10) Temperatures should be given in degrees Fahrenheit for this user. [F07+F14+F37]
- (2026-10-10) The user prefers temperatures reported in Fahrenheit. [F07+F37]
- (2026-10-12) The inspection API runs on port 8817. [F05+F10+F39]
- (2026-10-13) Bay BBQ passed its routine inspection with a score of 98. [F31+F40]
- (2026-10-14) Keep answers short: four sentences at most. [F42]
- (2026-10-15) The user wants reports as bullet points, at most five bullets. [F46]
- (2026-10-15) The user's HW6 report is due on October 20. [F34+F47]
- (2026-10-15) The user's supervisor is Dana Whitfield. [F32+F43]
- (2026-10-15) The user's GitHub repository is data260-7117. [F16+F44]
- (2026-10-15) The user covers the Willow Glen district. [F23+F45]
- (2026-10-16) The document database is s7117_doc on MongoDB. [F27+F49]
- (2026-10-16) The Golden Dragon follow-up inspection is November 10. [F50]
- (2026-10-16) Curry House had a rodent finding in dry storage and needs a follow-up within 7 days. [F36+F48]

## Resolved contradictions
- Golden Dragon's facility code: kept "Golden Dragon's facility code is FA0148210 (confirmed from the county permit)." (2026-09-20, F20) over "Golden Dragon's facility code is FA0148201 (assistant guess, unverified)." (2026-10-11, F38).
- Report format: kept "Reports for the user should be bullet points only, no more than five." (2026-10-15, F46) over "The user wants reports as bullet points, at most five bullets." (2026-10-03, F30).
- Golden Dragon follow-up inspection date: kept "Golden Dragon's follow-up inspection is November 10." (2026-10-16, F50) over "The Golden Dragon follow-up inspection is on November 3." (2026-10-01, F28); "The Golden Dragon follow-up moved to November 10 because a compressor part is delayed." (2026-10-14, F41).
