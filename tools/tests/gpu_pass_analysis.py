import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analyze_gpu_passes import analyze
class Stages(unittest.TestCase):
 def test_compute_is_not_vertex(self):
  d=analyze(dict(gpu_ticks_to_cpu_ns=1e6,rows=[dict(raw_gpu_ticks=[100,120,130,150]),dict(encoder_kind='compute',raw_gpu_ticks=[110,140,0,0])]))
  self.assertTrue(d['valid']);self.assertEqual(d['compute_union_ms'],30);self.assertEqual(d['vertex_union_ms'],20);self.assertEqual(d['fragment_union_ms'],20);self.assertEqual(d['all_render_stage_union_ms'],40)
 def test_clear_zero_stage_is_absent(self):
  d=analyze(dict(gpu_ticks_to_cpu_ns=1e6,rows=[dict(raw_gpu_ticks=[100,120,0,0])]))
  self.assertEqual(d['render_timestamp_extent_ms'],20);self.assertFalse(d['rows'][0]['fragment_present'])
 def test_bad_compute_timestamp_rejected(self):
  d=analyze(dict(gpu_ticks_to_cpu_ns=1e6,rows=[dict(encoder_kind='compute',raw_gpu_ticks=[140,110,0,0])]))
  self.assertFalse(d['valid'])
if __name__=='__main__':unittest.main()
