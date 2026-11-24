import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from geometry_measurement import validate_sample,frame_statistics
class Tests(unittest.TestCase):
 def sample(self):return {'pid':1,'geometry_control_session':'a','metal_lighting_requested':True,'metal_ssao_requested':True,'performance':{'geometry_timer_version':2,'skin_route':1,'cull_route':2,'geometry_validation_all':False,'thermal_state':0,'application_active':True,'settings_panel_open':False,'geometry_metal_state':2,'geometry_revision':2,'present_total':10,'present_time':3.0}}
 def test_reject_contaminated_windows(self):
  first=self.sample();self.assertEqual(validate_sample(first,[1,2],False),[])
  for key,value in [('low_power_mode',True),('thermal_state',1),('geometry_revision',3),('present_total',9),('present_time',2.0),('skin_failures',1),('cull_calibration_batches',1),('skin_validations',1),('pipeline_started',1),('settings_panel_open',True)]:
   d=copy.deepcopy(first);d['performance'][key]=value;self.assertTrue(validate_sample(d,[1,2],False,first),key)
  d=copy.deepcopy(first);d['geometry_control_session']='old';self.assertTrue(validate_sample(d,[1,2],False,first))
 def test_explicit_warm_condition(self):
  d=self.sample();d["performance"]["thermal_state"]=1
  self.assertTrue(validate_sample(d,[1,2],False))
  self.assertEqual(validate_sample(d,[1,2],False,thermal_state=1),[])
  d["performance"]["thermal_state"]=2
  self.assertTrue(validate_sample(d,[1,2],False,thermal_state=1))
 def test_raw_frames_not_hud_averages(self):
  rows=[{'sequence':i+10,'monotonic_s':t} for i,t in enumerate([1,1.1,1.3,1.6,2.0])];s=frame_statistics(rows,10,14)
  self.assertAlmostEqual(s['fps'],4);self.assertAlmostEqual(s['frame_mean_ms'],250);self.assertAlmostEqual(s['frame_median_ms'],250);self.assertAlmostEqual(s['frame_p95_ms'],400)
  with self.assertRaises(ValueError):frame_statistics(rows[1:],10,14)
  rows[2]['sequence']=11
  with self.assertRaises(ValueError):frame_statistics(rows,10,14)
if __name__=='__main__':unittest.main()
