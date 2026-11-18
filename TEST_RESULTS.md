# Validation results

Tested November 17, 2026.

- All **11 automated tests passed**: source coverage, rejection of unsourced email, duplicate flagging, explicit-group consolidation/conflict logging, scoring including negated ownership, HTML/mailto extraction, CSV round-trip and formula protection, robots-block logging, 100-row export preservation, ranked 25-row offline run, and completion/logging when live retrieval fails.
- The **full live 25-practice pipeline completed**. It retrieved 24 contact-source pages and logged one TLS protocol failure for MD-044. The failed request was not bypassed; the record retains its previous sourced research date and is flagged in the retrieval audit.
- The CRM output contains **25 unique lead IDs and 26 columns**. Scores are in descending order. There are **14 office emails, 25 named public point people, 21 blank ownership fields, 25 blank direct-person emails, and 25 blank EHR fields**.
- All **200 exported field assertions have source URLs**. No automatic duplicate candidates were found in the selected sample. Historical manual group consolidation is described in the methodology.
- Offline and live runs produced identical CRM values, as intended: extracted candidates do not silently replace reviewed assertions. The refresh audit records what was seen separately.
- NPPES discovery was not live-tested. The live test confirms retrieval/extraction execution, not that every existing fact appeared on the fetched contact page. A field may live on a separate roster/source page. Neither freshness, email deliverability nor decision authority was independently confirmed.

Reproduce automated checks with:

```sh
python3 -m unittest discover -s . -p 'test_*.py' -v
```
