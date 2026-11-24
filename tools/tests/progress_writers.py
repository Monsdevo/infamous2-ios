import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_progress_writers import decode


def e(kind, tag, a=0, b=0, time=1):
    return dict(kind=kind, who=tag, a=a, b=b, t0=time, t1=time+.000001)


def data(lanes):
    raw=b''.join(x.to_bytes(2, 'big') for x in lanes)
    return [int.from_bytes(raw[i:i+4], 'big') for i in range(0, 16, 4)]


def snapshot(target):
    a,b,c,d=data([4,5,5,5,6,6,6,6])
    return [e(300,1,0x12040,0x11000),e(301,1,0,0x370694),e(302,1,0x13000,target),
            e(303,1,a,b),e(304,1,c,d),e(305,1,1,2)]


def write(tag, lanes, mask=0xffff):
    a,b,c,d=data(lanes)
    return [e(320,tag,0x12040,0x12040),e(321,tag,8192,234),e(322,tag,0x1000,0x2000),
            e(323,tag,0,16),e(324,tag,mask,0x20),e(325,tag,a,b),e(326,tag,c,d)]


class ProgressWriters(unittest.TestCase):
    def test_lagging_is_sampled_not_guessed(self):
        result=decode(snapshot(6),{})
        self.assertEqual(result['snapshots'][0]['lagging_lanes'],[1,2,3])
        self.assertEqual(result['snapshots'][0]['minimum'],5)
        self.assertEqual(decode(snapshot(0xffffffff),{})['snapshots'][0]['lagging_lanes'],[])

    def test_only_covered_changed_lane_is_attributed(self):
        result=decode(write(2,[4,5,5,5,6,6,6,6])+write(3,[0,0,0,7,0,0,0,0],0xc0),{})
        self.assertEqual(result['writes'][1]['lane_values'],{'3':7})
        self.assertEqual(result['writes'][1]['changed_from_previous_spu_write_lanes'],[3])
        self.assertEqual(result['observed_lane_changes'][0]['lane'],3)
        self.assertEqual(decode(write(4,[0]*8,0x40),{})['writes'][0]['lane_values'],{})

    def test_incomplete_and_duplicate_are_visible(self):
        self.assertEqual(decode([e(300,1)],{})['incomplete_groups'],1)
        with self.assertRaises(ValueError):decode(snapshot(6)+[e(300,1)],{})


if __name__=='__main__':unittest.main()
