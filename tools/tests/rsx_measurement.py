import unittest,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rsx_measurement import validate_rsx
class Checks(unittest.TestCase):
 def sample(self):return {'cpu_profile_state':0,'performance':{'rsx_legacy_configured':1,'rsx_legacy_requested':1,'rsx_legacy_enabled':1,'rsx_legacy_debug_fallback':0,'rsx_legacy_methods':100,'rsx_legacy_state_skipped':80,'rsx_legacy_forwarded':20,'rsx_legacy_sync_forwarded':3,'rsx_legacy_draw_forwarded':4}}
 def test_mode_and_snapshot(self):
  d=self.sample();self.assertEqual(validate_rsx(d,True),[]);self.assertTrue(validate_rsx(d,False))
  for field,value in [('configured',0),('requested',0),('enabled',0),('debug_fallback',1),('methods',99),('sync_forwarded',21),('draw_forwarded',21)]:
   x=copy.deepcopy(d);x['performance']['rsx_legacy_'+field]=value;self.assertTrue(validate_rsx(x,True),field)
 def test_profiler_and_regression(self):
  d=self.sample();x=copy.deepcopy(d);x['cpu_profile_state']=1;self.assertTrue(validate_rsx(x,True))
  x=copy.deepcopy(d);x['performance']['rsx_legacy_methods']=99;x['performance']['rsx_legacy_forwarded']=19;self.assertTrue(validate_rsx(x,True,d))
 def test_reference(self):
  d=self.sample();d['performance'].update(rsx_legacy_requested=0,rsx_legacy_enabled=0,rsx_legacy_state_skipped=0,rsx_legacy_forwarded=100);self.assertEqual(validate_rsx(d,False),[])
if __name__=='__main__':unittest.main()
