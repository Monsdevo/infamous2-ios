#!/usr/bin/env python3
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from correlate_progress_cpu import owner_mapping,changed_after_snapshot

def writes(spu,lane,n):return [dict(row='0x100',spu_id=spu,changed_from_previous_spu_write_lanes=[lane],increased_from_previous_spu_write_lanes=[lane]) for _ in range(n)]
class Mapping(unittest.TestCase):
 def test_strict_and_shared_lane(self):
  p=dict(writes=writes(8192,2,60)+writes(8193,3,60)+writes(8192,1,400))
  m=owner_mapping(p,{8192:'100',8193:'101'},True)
  self.assertEqual({k:list(v['rows']['0x100']) for k,v in m.items()},{'100':['2'],'101':['3']})
  self.assertEqual(owner_mapping(p,{8192:'100',8193:'101'},False),{})
 def test_ambiguous_issuer(self):
  p=dict(writes=writes(8192,2,60)+writes(8193,2,60))
  self.assertEqual(owner_mapping(p,{8192:'100',8193:'101'},True),{})
 def test_missing_or_duplicate_native(self):
  p=dict(writes=writes(8192,2,60)+writes(8193,3,60))
  self.assertEqual(owner_mapping(p,{},True),{})
  self.assertEqual(owner_mapping(p,{8192:'100',8193:'100'},True),{})
 def test_change_then_reset_is_not_accepted(self):
  values=[(1,5),(2,6),(3,5)]
  self.assertTrue(changed_after_snapshot(values,[1,2,3],1,3,5))
  self.assertFalse(changed_after_snapshot(values,[1,2,3],3,4,5))
  self.assertFalse(changed_after_snapshot([],[],1,3,5))
 def test_small_or_mixed_sample(self):
  self.assertEqual(owner_mapping(dict(writes=writes(8192,2,49)),{8192:'100'},True),{})
  self.assertEqual(list(owner_mapping(dict(writes=writes(8192,2,60)+writes(8192,3,60)),{8192:'100'},True)['100']['rows']['0x100']),['2','3'])
if __name__=='__main__':unittest.main()
