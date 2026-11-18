# Pipeline Security Case A

Manhattan dermatology lead enrichment.

## Deliverables

1. **Working pipeline:** `pipeline.py`, Python 3.9 or newer, standard library only. No paid API, account or package installation needed.
2. **CRM sample:** `sample/manhattan_dermatology_25.csv`, 25 distinct practice/group leads selected from the 100 researched records by descending evidence fit score, then stable lead ID. It contains 25 phones and named point people, 14 office emails, and 200 supporting field assertions in `sample/evidence.csv`. All 25 direct-person email and EHR fields are blank. Ownership is unknown for 21.
3. **Methodology:** the short explanation below. `TEST_RESULTS.md` records validation and live retrieval results.

## Run it

Extract the bundle and run these commands from its folder:

```sh
# One-command pipeline: select, retrieve, extract, flag, score and export.
python3 pipeline.py run --sample-size 25 --output results

# Reproduce the supplied sample without internet access.
python3 pipeline.py run --sample-size 25 --offline --output results_offline

# Automated checks.
python3 -m unittest discover -s . -p 'test_*.py' -v
```

The live run uses the supplied reviewed practice dataset as its input. It writes a CRM CSV, field evidence, duplicate/merge reports, a retrieval audit and a run manifest. New emails/phones extracted from public pages are saved as review candidates in `refresh_audit.csv`; they do not overwrite sourced fields. Failed or blocked retrieval is logged and does not stop the export or advance the original review date. `--limit 3` restricts live checking to three selected records. `--sample-size 0` exports all 100.

Optional discovery: `python3 pipeline.py discover --output discovery` obtains NPPES dermatology provider candidates for New York. Review geography, practice identity and sources before promoting these candidates to `reviewed_leads.json`. NPPES discovery is separate from the default run and was not live-tested. Nothing schedules outreach, calls offices, sends email or updates a CRM.

## Sources, enrichment and trade-offs

**Sources.** The initial 100-practice dataset was researched on November 16, 2026 using official practice contact/team/location pages, supplemented by public professional directories, NPPES and company announcements. Some evidence came from indexed page excerpts. URLs, review dates and confidence accompany the records; the sample retains those research dates.

**Enrichment.** The reviewed dataset supplies practice identity, Manhattan office, telephone, named professional and stated role, published emails and their purpose, roster size where supported, and ownership assertions where available. The script retrieves the public contact source, honors robots exclusions, extracts visible text and mailto/tel links, and compares existing contact values with returned text. Named roles, ownership, roster scope and EHR require contextual review; this script does not automatically infer them from arbitrary new websites. Unknowns remain empty, and point people are not represented as confirmed purchasing decision-makers. High contact confidence denotes direct official-page evidence; Medium denotes reviewed public/indexed or supplemental evidence, not an accuracy probability.

**Deduplication.** Research consolidated known practice groups before export. The script merges identical practice records or records with an explicit reviewed group ID, logging conflicts and retaining the first representative office. Shared domains, phones or very similar names generate review flags. Shared buildings alone do not trigger a merge. The selected sample has no automatic duplicate flags. A possible UnionDerm/Vos relationship remains unconfirmed and is noted in its record.

**Priority.** Score = 30 for the reviewed Manhattan dermatology scope, +40 for an explicit physician-owned assertion, +20 for one listed provider or +30 for 2–10 providers; maximum 100. Unknown/larger counts earn no size bonus. This favors documented fit, so sparse evidence can depress a good practice's score.

**Trade-offs.** Human research provides contextual accuracy; automatic refresh provides reproducibility and change detection. This is not an autonomous discovery-to-verified-decision-maker system. Websites may be stale, block retrieval or require JavaScript. No inbox deliverability, operating status or purchasing authority was independently tested. The sample is not 25 proven independent businesses. Generic or restricted-purpose inboxes retain their labels. Preserve ZIP and phone columns as text when importing the UTF-8 CSV; map the included evidence fields to CRM custom fields as needed.
