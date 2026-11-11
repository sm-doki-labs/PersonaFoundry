import json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import form
class Flow(unittest.TestCase):
 def check(self,bad):
  with tempfile.TemporaryDirectory() as tmp:
   d=Path(tmp);out=d/'out'
   def put(k,v,many=False):
    (d/k).write_text('\n'.join(json.dumps(r) for r in v) if many else json.dumps(v))
   def row(c,m,who,txt):return dict(textId='src',convId=c,msgId=m,speaker=who,text=txt)
   put('tr',[row(c,c+k,s,t) for c in ['1','2'] for k,s,t in [('a','USER','ok?'),('b','SUBJECT','sure')]],True)
   put('ho',[row('hold','held','SUBJECT','heldout')],True);put('digest',{'piiFlags':[]})
   put('profile',dict(input_patterns=[],max_gap_seconds=1800,review_per_class=20));put('brief',dict(scene='test scene',role='test role'));(d/'facts').write_text('fixed fact')
   c=dict(section='VOICE',trigger='trigger',first='first',shift='shift',stop='stop',limit='limit',evidence=['1b'] if bad else ['1b','2b'],rule='State agreement briefly.')
   repo=Path(__file__).resolve().parents[2];compiler=Path(__file__).with_name('compiler.py')
   if not compiler.exists():compiler=repo/'src/character_factory_poc/stages/s8_prompts/evidence_compiler.py'
   argv=['form','--corpus',str(d/'tr'),'--holdout',str(d/'ho'),'--digest',str(d/'digest'),'--profile',str(d/'profile'),'--facts',str(d/'facts'),'--out',str(out),'--compiler',str(compiler),'--brief',str(d/'brief'),'--author','["fake-author"]','--reviewer','["fake-reviewer"]']
   with patch.object(sys,'argv',argv),patch.object(form,'ask',side_effect=[{'sections':[c]},{'decision':'accept','reason':'confirmed intended function'}]) as calls:
    if bad:
     with self.assertRaisesRegex(ValueError,'no valid candidates'):form.main()
     self.assertFalse((out/'최종프롬프트.md').exists());self.assertEqual(calls.call_count,1)
    else:
     form.main();self.assertIn(c['rule'],(out/'최종프롬프트.md').read_text());self.assertNotIn('sure',(out/'최종프롬프트.md').read_text());self.assertEqual(calls.call_count,2)
 def test_complete(self):self.check(False)
 def test_single_source_held_before_reviewer(self):self.check(True)
if __name__=='__main__':unittest.main()
