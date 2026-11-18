#!/usr/bin/env python3
"""Evidence-first Manhattan dermatology lead pipeline. Python 3.9+, standard library only.

build: validated, reproducible export from reviewed public-source assertions.
refresh: robots-aware public-page retrieval; suggestions require human review.
discover: public NPPES candidate discovery; registry records are NOT verified practices.
run: select a ranked sample, refresh public pages, validate and export in one command.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENT = 'PracticeLeadResearch/1.0'
EMAIL = re.compile(r'[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}', re.I)
PHONE = re.compile(r'(?<!\d)(?:\+1[ .\-]?)?\(?\d{3}\)?[ .\-]\d{3}[ .\-]\d{4}(?!\d)')

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def norm(s):
    return re.sub(r'[^a-z0-9]', '', str(s).lower())

def domain(s):
    return urllib.parse.urlparse(s).netloc.lower().removeprefix('www.')

def score(row):
    # Evidence lower bound, not a probability or actual practice quality measure.
    n = row.get('provider_count') or 0
    owned = row.get('ownership', '').strip().lower().startswith('physician-owned')
    return 30 + (40 if owned else 0) + (20 if n == 1 else 30 if 2 <= n <= 10 else 0)

def duplicate_candidates(rows):
    pairs = []
    for i, a in enumerate(rows):
        for b in rows[i+1:]:
            reasons = []
            if a.get('website') and b.get('website') and domain(a['website']) == domain(b['website']):
                reasons.append('same website domain')
            if a.get('phone') and norm(a['phone']) == norm(b.get('phone', '')):
                reasons.append('same phone')
            if SequenceMatcher(None, norm(a['name']), norm(b['name'])).ratio() >= .92:
                reasons.append('very similar name')
            if reasons:
                pairs.append({'lead_a': a['id'], 'lead_b': b['id'], 'reasons': '; '.join(reasons)})
    return pairs

def validate(rows):
    errors = []
    seen = set()
    for row in rows:
        ident = row.get('id', '')
        if not ident or ident in seen:
            errors.append(f'Duplicate/missing lead ID: {ident}')
        seen.add(ident)
        for field in ('name', 'source', 'address', 'zip', 'phone', 'checked_on'):
            if not row.get(field):
                errors.append(f'{ident}: missing required {field}')
        if row.get('borough') != 'Manhattan' or not re.fullmatch(r'10[01]\d{2}', row.get('zip', '')):
            errors.append(f'{ident}: geography needs review')
        for field in ('email', 'contact_email', 'partnership_email'):
            if row.get(field) and not EMAIL.fullmatch(row[field]):
                errors.append(f'{ident}: invalid email in {field}')
        for field, source in (('email', 'email_source'), ('contact_email', 'contact_email_source'), ('ownership', 'ownership_source')):
            if row.get(field) and not row.get(source):
                errors.append(f'{ident}: {field} lacks provenance')
        if row.get('contact') and not row.get('enrichment_source'):
            errors.append(f'{ident}: point person lacks provenance')
        if row.get('provider_count') and not row.get('count_scope'):
            errors.append(f'{ident}: provider count lacks scope')
    if errors:
        raise ValueError('\n'.join(errors))

def evidence(rows):
    output = []
    for row in rows:
        sources = {
            'name': row['source'], 'address': row['source'], 'zip': row['source'],
            'phone': row.get('phone_source') or row['source'],
            'email': row.get('email_source'), 'email_use': row.get('email_source'),
            'contact': row.get('enrichment_source'), 'role': row.get('enrichment_source'),
            'contact_email': row.get('contact_email_source'),
            'ownership': row.get('ownership_source'),
            'provider_count': row.get('enrichment_source'),
            'partnership_email': row.get('enrichment_source') if row['id'] == 'MD-042' else row.get('source'),
        }
        for field, source in sources.items():
            value = row.get(field, '')
            if value == '' or value is None:
                continue
            confidence = 'Medium — reviewed public assertion; current operation not independently tested'
            if field in ('name', 'address', 'zip', 'phone') and row.get('contact_confidence', '').startswith('High'):
                confidence = 'High — directly retrieved official page'
            if field == 'email' and row.get('email_confidence'):
                confidence = row['email_confidence']
            caveat = row.get('notes', '')
            if field == 'provider_count':
                caveat = row.get('count_scope', '') + '; website roster, not audited headcount.'
            if field in ('contact', 'role', 'contact_email'):
                caveat += ' Published affiliation/role only; verify current role and decision authority.'
            if 'email' in field:
                caveat += ' Mailbox deliverability not tested; respect published purpose.'
            output.append({'lead_id': row['id'], 'field': field, 'value': value, 'source_url': source or '', 'confidence': confidence, 'reviewed_on': row['checked_on'], 'caveat': caveat.strip()})
    return output

def write_csv(path, headers, records):
    # Proper CSV quoting, blank unknowns; protect spreadsheet formula interpretation.
    def safe(v):
        if isinstance(v, str) and v.startswith(('=', '+', '-', '@')):
            return "'" + v
        return '' if v is None else v
    with Path(path).open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in records:
            writer.writerow([safe(v) for v in row])

def build(args):
    rows = read_json(args.input)
    schema = read_json(ROOT / 'schema.json')
    validate(rows)
    for row in rows:
        row['fit_score'] = score(row)
        row['missing_fields'] = '; '.join(k for k in ('email', 'contact', 'contact_email', 'ownership', 'provider_count', 'ehr') if not row.get(k))
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / f'manhattan_dermatology_{len(rows)}.csv', schema['headers'], [[row.get(k, '') for k in schema['keys']] for row in rows])
    assertions = evidence(rows)
    fields = ['lead_id', 'field', 'value', 'source_url', 'confidence', 'reviewed_on', 'caveat']
    write_csv(out / 'evidence.csv', fields, [[r[k] for k in fields] for r in assertions])
    dupes = duplicate_candidates(rows)
    write_json(out / 'duplicate_review.json', dupes)
    report = {'practices_or_groups': len(rows), 'public_office_emails': sum(bool(r.get('email')) for r in rows), 'named_points_of_contact': sum(bool(r.get('contact')) for r in rows), 'public_point_person_emails': sum(bool(r.get('contact_email')) for r in rows), 'partnership_or_assistant_inboxes': sum(bool(r.get('partnership_email')) for r in rows), 'unknown_ownership': sum(not bool(r.get('ownership')) for r in rows), 'unknown_ehr': sum(not bool(r.get('ehr')) for r in rows), 'assertions': len(assertions), 'duplicate_candidates': len(dupes), 'verification': 'Reviewed public websites and published directories; no calls or email deliverability tests; cached search excerpts included.'}
    write_json(out / 'validation_report.json', report)
    print(json.dumps(report, indent=2))

class PublicText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        for key, value in attrs:
            if key == 'href' and value and value.startswith(('mailto:', 'tel:')):
                self.parts.append(urllib.parse.unquote(value.split(':', 1)[1].split('?')[0]))
    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

def fetch(url, maximum=2_000_000):
    if urllib.parse.urlparse(url).scheme not in ('http', 'https'):
        raise ValueError('Only HTTP(S) public URLs accepted')
    req = urllib.request.Request(url, headers={'User-Agent': AGENT})
    with urllib.request.urlopen(req, timeout=20) as res:
        data = res.read(maximum + 1)
        if len(data) > maximum:
            raise ValueError('Response too large')
        return res.geturl(), res.headers.get('Content-Type', ''), data.decode('utf-8', errors='replace')

def refresh(args):
    rows = read_json(args.input)
    selected = rows[:args.limit] if args.limit else rows
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    results = []; robots_cache = {}; last_request = {}
    for row in selected:
        url = row.get('source')
        host = urllib.parse.urlparse(url)
        origin = f'{host.scheme}://{host.netloc}'
        result = {'lead_id': row['id'], 'url': url, 'attempted_at': dt.datetime.now(dt.timezone.utc).isoformat()}
        try:
            if origin not in robots_cache:
                rp = urllib.robotparser.RobotFileParser()
                try:
                    _, _, txt = fetch(origin + '/robots.txt')
                    rp.parse(txt.splitlines())
                except urllib.error.HTTPError as exc:
                    if exc.code != 404:
                        raise
                    rp.parse([])
                robots_cache[origin] = rp
                last_request[origin] = time.monotonic()
            rp = robots_cache[origin]
            if not rp.can_fetch(AGENT, url):
                result['status'] = 'skipped_robots'; results.append(result); continue
            delay = max(args.delay, rp.crawl_delay(AGENT) or 0)
            time.sleep(max(0, delay - (time.monotonic() - last_request.get(origin, 0))))
            final_url, content_type, html = fetch(url)
            last_request[origin] = time.monotonic()
            result.update({'final_url': final_url, 'content_type': content_type, 'sha256': hashlib.sha256(html.encode()).hexdigest()})
            if 'html' not in content_type and not content_type.startswith('text/'):
                result['status'] = 'manual_review_non_html'; results.append(result); continue
            parser = PublicText(); parser.feed(html)
            text_body = '\n'.join(parser.parts)
            (out / (row['id'] + '.txt')).write_text(text_body, encoding='utf-8')
            result.update({'status': 'retrieved_review_required', 'candidate_emails': sorted(set(EMAIL.findall(text_body))), 'candidate_phones': sorted(set(PHONE.findall(text_body))), 'existing_email_seen': bool(row.get('email')) and row['email'].lower() in text_body.lower(), 'existing_phone_seen': norm(row['phone']) in norm(text_body), 'existing_point_person_seen': bool(row.get('contact')) and norm(row['contact']) in norm(text_body)})
        except Exception as exc:
            result.update({'status': 'unavailable_review_required', 'error': str(exc)})
        results.append(result)
        write_json(out / 'refresh_review.json', results)
    write_json(out / 'refresh_review.json', results)
    print(f'{len(results)} retrieval results saved. Review suggestions before updating reviewed_leads.json. No dates or assertions were auto-promoted.')
    return results

def consolidate(rows):
    """Merge only explicitly curated group IDs or identical practice records.

    Similar names/shared phones remain review candidates; conflicting values are logged.
    The first record is the representative office, preserving its field provenance.
    """
    kept, index, merged = [], {}, []
    for row in rows:
        key = ('group', row['group_id']) if row.get('group_id') else (
            'exact', norm(row['name']), domain(row.get('website', '')),
            norm(row.get('phone', '')), norm(row.get('address', '')))
        if key not in index:
            index[key] = row
            kept.append(row)
            continue
        representative = index[key]
        conflicts = {k: {'retained': representative.get(k), 'alternate': v}
                     for k, v in row.items() if k != 'id' and v not in ('', None)
                     and representative.get(k) not in ('', None, v)}
        merged.append({'retained_id': representative['id'], 'merged_id': row['id'],
                       'reason': key[0], 'conflicts': conflicts})
    return kept, merged

def run(args):
    """Reproducible reviewed-source pipeline with optional live retrieval."""
    all_rows = read_json(args.input)
    validate(all_rows)
    unique, merged = consolidate(all_rows)
    ranked = sorted(unique, key=lambda r: (-score(r), r['id']))
    selected = ranked[:args.sample_size] if args.sample_size else ranked
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    snapshot = out / 'selected_leads.json'
    if snapshot.resolve() == Path(args.input).resolve():
        raise ValueError('Choose a different output folder to preserve the input')
    write_json(snapshot, selected)
    write_json(out / 'merged_records.json', merged)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    if args.offline:
        results = [{'lead_id': r['id'], 'url': r['source'],
                    'status': 'not_refreshed_offline', 'attempted_at': ''} for r in selected]
        write_json(out / 'refresh' / 'refresh_review.json', results)
    else:
        results = refresh(argparse.Namespace(input=snapshot, output=out / 'refresh',
                                             limit=args.limit, delay=args.delay))
    fields = ['lead_id', 'url', 'status', 'attempted_at', 'existing_phone_seen',
              'existing_email_seen', 'existing_point_person_seen', 'candidate_emails',
              'candidate_phones', 'error']
    write_csv(out / 'refresh_audit.csv', fields,
              [[('; '.join(result.get(k, [])) if k.startswith('candidate_') else result.get(k, ''))
                for k in fields] for result in results])
    build(argparse.Namespace(input=snapshot, output=out))
    counts = {}
    for result in results:
        status = result['status']
        counts[status] = counts.get(status, 0) + 1
    write_json(out / 'run_manifest.json', {
        'started_at': started, 'input_records': len(all_rows), 'merged_records': len(merged),
        'exported_records': len(selected), 'sample_size_requested': args.sample_size,
        'selection': 'Descending evidence fit score; stable lead ID breaks ties',
        'mode': 'offline_reviewed_snapshot' if args.offline else 'public_page_refresh',
        'refresh_status_counts': counts, 'not_attempted': len(selected) - len(results),
        'input_sha256': hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),
        'limitation': 'Newly extracted contacts are review candidates. Reviewed fields and dates are never automatically promoted. Failed retrieval does not establish closure or invalidate prior evidence.'})
    print(f'Completed: {len(selected)} practices exported to {out}. No outreach sent.')

def discover(args):
    all_results = []
    for skip in range(0, 1200, 200):
        query = urllib.parse.urlencode({'version': '2.1', 'taxonomy_description': 'Dermatology', 'state': 'NY', 'city': 'New York', 'limit': 200, 'skip': skip})
        _, _, body = fetch('https://npiregistry.cms.hhs.gov/api/?' + query)
        result = json.loads(body)
        if result.get('Errors'):
            raise ValueError(str(result['Errors']))
        batch = result.get('results', [])
        all_results.extend(batch)
        if len(batch) < 200:
            break
        time.sleep(args.delay)
    write_json(Path(args.output) / 'nppes_candidates.json', {'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'warning': 'Provider/registry candidates only. Check actual Manhattan office, operating status, practice group and ownership before promotion.', 'results': all_results})
    print(f'{len(all_results)} NPPES candidate records saved; these are not additional verified leads.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'refresh', 'discover', 'run'], nargs='?', default='build')
    parser.add_argument('--input', default=str(ROOT / 'reviewed_leads.json'))
    parser.add_argument('--output', default=str(ROOT / 'output'))
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--delay', type=float, default=1.5)
    parser.add_argument('--sample-size', type=int, default=25, help='run: ranked practice count; 0 selects all')
    parser.add_argument('--offline', action='store_true', help='run: export reviewed snapshot without web requests')
    args = parser.parse_args()
    if args.limit < 0 or args.delay < 0 or args.sample_size < 0:
        parser.error('limit, delay and sample size must be nonnegative')
    {'build': build, 'refresh': refresh, 'discover': discover, 'run': run}[args.command](args)

if __name__ == '__main__':
    main()
