import unittest
from analyze_frame_dependencies import match_writers


def event(kind,who,a,b,t0,t1):return dict(kind=kind,who=who,a=a,b=b,t0=t0,t1=t1)
def write(tag,value,t):
    return [event(21,tag,0x870,value,t,t+.001),event(22,tag,8192,234,t,t+.001),
            event(23,tag,0x7320,0x7210,t,t+.001),event(24,tag,0x100,4,t,t+.001)]


class Dependencies(unittest.TestCase):
    def test_value_and_temporal_dependency(self):
        events=write(1,7,1.5)+write(2,8,2.5)+[event(5,0,0x870,7,1,2),event(5,0,0x870,7,3,4)]
        r=match_writers(events,{})
        self.assertEqual(r['match_counts'],{'unique':1,'unmatched':1})
        self.assertEqual(r['producers'][0]['image_id'],234)
        self.assertAlmostEqual(r['acquire_poll_delay_ms']['median'],499)
    def test_ambiguity_and_incomplete_not_guessed(self):
        events=write(1,7,1.4)+write(2,7,1.5)+[event(5,0,0x870,7,1,2),event(21,3,0x890,7,1.5,1.6)]
        r=match_writers(events,{})
        self.assertEqual(r['match_counts'],{'ambiguous':1})
        self.assertEqual(r['incomplete_groups'],1)
        self.assertEqual(r['producers'],[])
