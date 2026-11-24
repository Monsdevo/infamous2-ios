import csv,json,tempfile,unittest
from pathlib import Path
from analyze_critical_job import analyze

def fixture(path,change=False,ambiguous=False,logical=False):
 events=[]
 def emit(k,who,a,b,t0,t1=None):events.append(dict(kind=k,who=who,a=a,b=b,start_s=t0,end_s=t0 if t1 is None else t1))
 def pair(data):return int.from_bytes(data[:4],'big'),int.from_bytes(data[4:],'big')
 def data(value):return b''.join(x.to_bytes(2,'big') for x in (0,200,value,200,200,200,200,200))
 emit(18,8192|0x80000000,77,0,.001)
 if ambiguous:emit(18,8192|0x80000000,88,0,.002)
 for i in range(61):
  t=.01+i*.01;tag=i+1;d=data(i)
  for k,a,b in ((320,0x20000,0x20000),(321,8192,100),(322,0x3450,0),(323,0,16),(324,65535,32),(325,*pair(d[:8])),(326,*pair(d[8:]))):emit(k,tag,a,b,t)
 if change:
  t=1.500025;tag=62;d=data(61)
  for k,a,b in ((320,0x20000,0x20000),(321,8192,100),(322,0x3450,0),(323,0,16),(324,65535,32),(325,*pair(d[:8])),(326,*pair(d[8:]))):emit(k,tag,a,b,t)
 target=0xC0018F90 if logical else 0x6b90
 emit(400,999,target,8192,1)
 fields={401:(target,8192),402:(10000000,0),403:(77,0),404:(0x866c,0x866c),405:(3,4),406:(1,1),407:(1234,0),408:(1,1),409:(234,100)}
 if logical:fields.update({410:(200,200),411:(0,0),412:(100,100)});fields[406]=(1,2)
 for k,(a,b) in fields.items():emit(k,999,a,b,1,2)
 d=data(60)
 for k,a,b in ((310,0x20000,100),(311,*pair(d[:8])),(312,*pair(d[8:]))):emit(k,777,a,b,1.5,1.50005)
 emit(313,777,0x370694,0,1.500051,1.500052)
 for t in (.5,1,1.5,2,2.5):emit(9,1,0,0,t)
 emit(15,1,0,0,.6,2.6)
 with path.open('w') as f:
  f.write('# '+json.dumps(dict(start=0,end=3,rows=len(events),dropped=0))+'\n')
  w=csv.DictWriter(f,fieldnames=('kind','who','a','b','start_s','end_s'));w.writeheader();w.writerows(events)

class CriticalJobTests(unittest.TestCase):
 def test_nested_time_is_not_added_to_root_and_dependency_is_observed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'trace.csv';fixture(p);r,_=analyze(p)
   self.assertEqual(r['root_calls'],1);self.assertEqual(r['poll_counts']['qualified'],1)
   self.assertAlmostEqual(r['root_linked_qualified_poll_union_ms'],.05)
   self.assertEqual(r['targets']['0x6b90']['inclusive_thread_cpu_ms']['median'],10)
 def test_logical_job_entry_and_guest_return_survive_native_depth_change(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'trace.csv';fixture(p,logical=True);r,_=analyze(p)
   self.assertTrue(r['whole_job_scopes']);self.assertEqual(r['root_calls'],1)
   self.assertIn('jobmod_1774dd41c4e8_e14f90',r['targets'])
   self.assertAlmostEqual(r['root_linked_qualified_poll_union_ms'],.05)
 def test_observed_changes_during_poll_are_not_attributed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'trace.csv';fixture(p,change=True);r,_=analyze(p)
   self.assertEqual(r['root_linked_qualified_poll_union_ms'],0)
   self.assertEqual(r['poll_counts']['qualified'],0)
 def test_conflicting_native_mapping_is_not_attributed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'trace.csv';fixture(p,ambiguous=True);r,_=analyze(p)
   self.assertEqual(r['root_linked_qualified_poll_union_ms'],0)
   self.assertEqual(r['poll_counts']['qualified'],0)
 def test_wrong_guest_return_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'trace.csv';fixture(p,logical=True)
   text=p.read_text();self.assertIn('404,999,34412,34412,',text)
   p.write_text(text.replace('404,999,34412,34412,','404,999,34412,34416,'))
   with self.assertRaisesRegex(ValueError,'expected PC'):analyze(p)
 def test_missing_interior_return_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'trace.csv';fixture(p,logical=True)
   lines=p.read_text().splitlines();meta=json.loads(lines[0][2:])
   lines=[line for line in lines if not line.startswith('409,999,')]
   meta['rows']-=1;lines[0]='# '+json.dumps(meta);p.write_text('\n'.join(lines)+'\n')
   with self.assertRaisesRegex(ValueError,'Unclosed scope'):analyze(p)

if __name__=='__main__':unittest.main()
