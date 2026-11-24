import json
from pathlib import Path
import tempfile
import unittest
from analyze_frame_trace import analyze,union_seconds

class TraceTests(unittest.TestCase):
    def test_nested_spans_are_not_added(self):
        self.assertAlmostEqual(union_seconds([(0,1),(.2,.5),(.8,1.5)],0,2),1.5)
        self.assertAlmostEqual(union_seconds([(0,1)],.4,.6),.2)
    def test_frame_gpu_uses_actual_not_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'trace.csv'
            rows=['9,0,0,0,1,1','9,0,0,0,2,2','15,1,10,4,1.2,1.4','15,2,10,4,1.3,1.5','14,0,0,0,1,2']
            meta={'start':0,'end':3,'rows':len(rows),'dropped':0}
            p.write_text('# '+json.dumps(meta)+'\nkind,who,a,b,start_s,end_s\n'+'\n'.join(rows)+'\n')
            report,_=analyze(p)
            self.assertAlmostEqual(report['frame_windows'][0]['gpu_busy_union_ms'],300)
            meta['dropped']=1;p.write_text('# '+json.dumps(meta)+'\nkind,who,a,b,start_s,end_s\n'+'\n'.join(rows)+'\n')
            with self.assertRaises(ValueError):analyze(p)
if __name__=='__main__':unittest.main()
