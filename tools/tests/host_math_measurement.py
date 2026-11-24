#!/usr/bin/env python3
"""Reject mixed-mode/validation windows rather than report misleading FPS."""
import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from measure_host_research import errors
ROOT=Path(__file__).resolve().parents[2]
class Guards(unittest.TestCase):
 def setUp(self):
  self.row=json.loads((ROOT/'out/host-research/gain40-06/mask-interval/A-reference/000.json').read_text())
  self.scene=json.loads((ROOT/'out/host-research/gain40-06/scene-ready.json').read_text())
  self.row['spu_math']=dict(mode=1,validated=25,mismatches=0)
 def test_current_mode(self):
  self.assertEqual(errors(self.row,None,0,self.scene,light_far=1,spu_math=1),[])
  self.assertIn('SPU math mode differs/faulted',errors(self.row,None,0,self.scene,light_far=1,spu_math=0))
 def test_late_validation(self):
  first=copy.deepcopy(self.row);self.row['monotonic_s']+=1;self.row['spu_math']['validated']+=1
  self.assertIn('SPU math validation during FPS window',errors(self.row,first,0,self.scene,light_far=1,spu_math=1))
 def test_latched_mismatch(self):
  self.row['spu_math']['mismatches']=1
  self.assertIn('SPU math mode differs/faulted',errors(self.row,None,0,self.scene,light_far=1,spu_math=1))
if __name__=='__main__':unittest.main()
