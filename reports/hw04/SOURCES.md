# HW04 — RAG Corpus Sources

Six documents. Files 1–4 are the cleaned HW3 corpus (`data/corpus/*.txt`, sources in
`reports/hw03/SOURCES.md`); files 5–6 were added for HW4 (`data/corpus/hw04/`), fetched as plain
text from the Wikipedia API on 2026-09-28 (the reference/"See also" sections were dropped).

| # | File | Source | Notes |
|---|---|---|---|
| 1 | `retail-food-inspection-guide.txt` | LA County DPH, Retail Food Inspection Guide (Oct 2025) | 218 chunks |
| 2 | `abc-retail-food-inspection-guide.pdf.txt` | San Bernardino County EHS, ABC Retail Food Inspection Guide (2018) | 78 chunks |
| 3 | `print.txt` | Sacramento County inspection report, Pioneer House (FA0005532) | 2 chunks |
| 4 | `print1.txt` | Sacramento County inspection report, Dat Thanh Restaurant (FA0003611) | 4 chunks |
| 5 | `hw04/wikipedia-danger-zone-food-safety.txt` | https://en.wikipedia.org/wiki/Danger_zone_(food_safety), revision 1374631635, CC BY-SA 4.0 | 3 chunks |
| 6 | `hw04/wikipedia-restaurant-rating.txt` | https://en.wikipedia.org/wiki/Restaurant_rating, revision 1362168917, CC BY-SA 4.0 | 3 chunks |
