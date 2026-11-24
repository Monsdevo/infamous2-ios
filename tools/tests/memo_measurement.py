import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from memo_measurement import validate_memo,FIELDS

class Gates(unittest.TestCase):
    def sample(self):
        return {'renderer_memo_control_enabled':True,'cpu_profile_state':0,'frame_trace_state':3,
            'renderer_memo':{k:{**{f:0 for f in FIELDS},'mode':m} for k,m in [('vertex',1),('texture',0)]}}
    def test_modes_and_validation(self):
        d=self.sample();self.assertEqual(validate_memo(d,(1,0)),[])
        d['renderer_memo']['vertex']['mode']=2
        self.assertTrue(validate_memo(d,(2,0)));self.assertEqual(validate_memo(d,(2,0),correctness=True),[])
    def test_work_and_faults(self):
        a=self.sample();d=copy.deepcopy(a);s=d['renderer_memo']['vertex'];s.update(calls=10,lookups=10,hits=8,misses=2)
        self.assertEqual(validate_memo(d,(1,0),a),[])
        s['validations']=1;self.assertTrue(validate_memo(d,(1,0),a))
        s['validations']=0;s['mismatches']=1;self.assertTrue(validate_memo(d,(1,0),a))
        s['mismatches']=0;s['hits']=9;self.assertTrue(validate_memo(d,(1,0),a))
    def test_memory_and_profiler(self):
        d=self.sample();d['cpu_profile_state']=1;self.assertTrue(validate_memo(d,(1,0)))
        d['cpu_profile_state']=3;d['renderer_memo']['texture']['resident_bytes']=128*1024*1024+1
        self.assertTrue(validate_memo(d,(1,0)))
        d=self.sample();a=copy.deepcopy(d);d['runtime_log_capped']=True
        self.assertTrue(validate_memo(d,(1,0),a))

if __name__=='__main__':unittest.main()
