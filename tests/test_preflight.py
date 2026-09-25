import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ops'))
spec = importlib.util.spec_from_file_location('preflight', ROOT / 'ops/preflight-exl3.py')
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class Preflight(unittest.TestCase):
    def test_gpu_architecture_count_and_occupied_memory(self):
        row = 'NVIDIA H200, 9.0, 143771, 143000\n'
        preflight.check_gpus(row * 2, 2)
        for output, tp in [(row, 2), (row * 2, 1), (row.replace('9.0', '10.0') * 2, 2),
                           (row.replace('H200', 'B200') * 2, 2),
                           (row.replace('143000', '10000') * 2, 2)]:
            with self.subTest(output=output, tp=tp), self.assertRaises(ValueError):
                preflight.check_gpus(output, tp)

    def test_resume_budget_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            spec = {'files': [{'name': 'part', 'size': 10}]}
            self.assertEqual(preflight.remaining_bytes(spec, root), 10)
            (root / 'part').write_bytes(b'abc')
            self.assertEqual(preflight.remaining_bytes(spec, root), 7)
            (root / 'part').unlink()
            (root / 'part').symlink_to(root.parent / 'outside')
            with self.assertRaises(ValueError):
                preflight.remaining_bytes(spec, root)

    def test_stage_rejects_unknown_before_reading_profile(self):
        p = subprocess.run(['bash', str(ROOT / 'ops/exl3.sh'), str(ROOT / 'README.md'), 'wrong'],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn('Unknown stage', p.stderr)


if __name__ == '__main__':
    unittest.main()
