import unittest
from followup import windows
def row(i,s,t,conv='a',at='2026-01-01T01:00:00'):
 return dict(textId='x',convId=conv,msgId=str(i),speaker=s,text=t,at=at)
def gen(data,ban=None,flags=None):return list(windows(data,ban or (set(),set()),flags or set()))
class Followup(unittest.TestCase):
 def test_full_window_and_join(self):
  a=[row(i,s,t) for i,(s,t) in enumerate([('USER','a'),('SUBJECT','b'),('USER','c'),('USER','more'),('SUBJECT','d')])]
  self.assertEqual(gen(a)[0]['turns'],['a','b','c more','d']);self.assertEqual(gen(a)[0]['id'],'4');self.assertEqual(gen(a[:-1]),[])
 def test_no_bridge(self):
  a=[row(i,['USER','SUBJECT'][i%2],str(i)) for i in range(4)]
  for changed in [dict(a[2],speaker='UNKNOWN'),dict(a[2],text='https://example.test'),dict(a[2],at='2026-01-01T19:00:00'),dict(a[2],convId='other')]:
   self.assertEqual(gen(a[:2]+[changed]+a[3:]),[])
  self.assertEqual(gen(a,flags={'1'}),[]);self.assertEqual(gen(a,ban=({('x','a')},set())),[])
  with self.assertRaises(ValueError):gen(a,ban=(set(),{'2'}))
if __name__=='__main__':unittest.main()
