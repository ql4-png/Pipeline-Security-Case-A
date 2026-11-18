import argparse
import copy
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pipeline as p


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.rows = p.read_json(p.ROOT / 'reviewed_leads.json')

    def test_sample_integrity(self):
        p.validate(self.rows)
        self.assertEqual(len(self.rows), 100)
        self.assertEqual(len({r['id'] for r in self.rows}), 100)
        self.assertTrue(all(r.get('contact') for r in self.rows))
        self.assertTrue(all(r.get('source') and r.get('enrichment_source') for r in self.rows))
        self.assertTrue(all(not r.get('ehr') for r in self.rows))
        self.assertTrue(all(e['source_url'] for e in p.evidence(self.rows)))

    def test_unsourced_email_rejected(self):
        row = copy.deepcopy(self.rows[0])
        row.update(email='office@example.com', email_source='')
        with self.assertRaisesRegex(ValueError, 'email lacks provenance'):
            p.validate([row])

    def test_duplicate_group_detected_but_shared_address_not_merged(self):
        a = dict(id='a', name='North Dermatology', website='https://north.example', phone='2121111111', address='1 Main St')
        b = dict(id='b', name='South Skin', website='https://south.example', phone='2122222222', address='1 Main St')
        self.assertEqual(p.duplicate_candidates([a, b]), [])
        b['website'] = 'https://www.north.example/contact'
        self.assertIn('same website domain', p.duplicate_candidates([a, b])[0]['reasons'])

    def test_score_requires_recorded_ownership_and_size(self):
        self.assertEqual(p.score({}), 30)
        self.assertEqual(p.score({'provider_count': 1}), 50)
        self.assertEqual(p.score({'ownership': 'Physician-owned', 'provider_count': 4}), 100)
        self.assertEqual(p.score({'provider_count': 25}), 30)
        self.assertEqual(p.score({'ownership': 'Not physician-owned'}), 30)

    def test_public_text_ignores_scripts_and_reads_mailto(self):
        parser = p.PublicText()
        parser.feed('<script>private@example.com</script><a href="mailto:office@example.com?subject=Hello">Email</a><p>212-555-0123</p>')
        body = '\n'.join(parser.parts)
        self.assertNotIn('private@example.com', body)
        self.assertEqual(p.EMAIL.findall(body), ['office@example.com'])
        self.assertEqual(p.PHONE.findall(body), ['212-555-0123'])

    def test_csv_roundtrip_and_formula_safety(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.csv'
            p.write_csv(path, ['name', 'blank', 'literal'], [['A, B\nClinic', None, '=1+1']])
            with path.open(encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[1], ['A, B\nClinic', '', "'=1+1"])

    def test_robots_block_is_saved_and_does_not_fetch_page(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(input=p.ROOT / 'reviewed_leads.json', output=directory, limit=1, delay=0)
            with patch.object(p, 'fetch', return_value=('https://example.com/robots.txt', 'text/plain', 'User-agent: *\nDisallow: /')) as mock:
                p.refresh(args)
            self.assertEqual(mock.call_count, 1)
            self.assertEqual(p.read_json(Path(directory) / 'refresh_review.json')[0]['status'], 'skipped_robots')

    def test_build_preserves_unknowns_and_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            p.build(argparse.Namespace(input=p.ROOT / 'reviewed_leads.json', output=directory))
            with (Path(directory) / 'manhattan_dermatology_100.csv').open(encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 100)
            self.assertEqual(sum(bool(r['Public office email']) for r in rows), 49)
            self.assertEqual(sum(bool(r['Point-person email']) for r in rows), 5)
            self.assertTrue(all(r['EHR'] == '' for r in rows))

    def test_group_consolidation_preserves_source_and_logs_conflicts(self):
        a, b = copy.deepcopy(self.rows[:2])
        a['group_id'] = b['group_id'] = 'explicit-reviewed-group'
        kept, merged = p.consolidate([a, b])
        self.assertEqual(kept, [a])
        self.assertEqual(merged[0]['merged_id'], b['id'])
        self.assertEqual(merged[0]['conflicts']['source']['retained'], a['source'])

    def test_run_offline_produces_ranked_25_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(input=p.ROOT / 'reviewed_leads.json', output=directory,
                                      sample_size=25, offline=True, limit=0, delay=0)
            with patch.object(p, 'fetch', side_effect=AssertionError('offline network access')):
                p.run(args)
            out = Path(directory)
            with (out / 'manhattan_dermatology_25.csv').open(encoding='utf-8-sig', newline='') as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 25)
            scores = [int(r['Evidence fit / 100']) for r in rows]
            self.assertEqual(scores, sorted(scores, reverse=True))
            self.assertEqual(p.read_json(out / 'run_manifest.json')['mode'], 'offline_reviewed_snapshot')
            self.assertEqual(p.read_json(out / 'selected_leads.json')[0]['checked_on'], '2026-11-16')

    def test_live_run_logs_failure_without_promoting_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(input=p.ROOT / 'reviewed_leads.json', output=directory,
                                      sample_size=1, offline=False, limit=0, delay=0)
            with patch.object(p, 'fetch', side_effect=OSError('network unavailable')):
                p.run(args)
            out = Path(directory)
            manifest = p.read_json(out / 'run_manifest.json')
            self.assertEqual(manifest['refresh_status_counts'], {'unavailable_review_required': 1})
            self.assertTrue((out / 'manhattan_dermatology_1.csv').exists())
            self.assertEqual(p.read_json(out / 'selected_leads.json')[0]['checked_on'], '2026-11-16')


if __name__ == '__main__':
    unittest.main()
