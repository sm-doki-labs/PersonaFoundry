import unittest
from prepare import extract
PROFILE={'input_patterns':[], 'max_gap_seconds':1800}
def msg(conv,id,sp,text,at='2026-01-01T09:00:00'):
 return dict(textId='synthetic',convId=conv,msgId=id,speaker=sp,text=text,at=at)
class SourceBoundary(unittest.TestCase):
 def test_shared_session_and_gaps_do_not_create_evidence(self):
  rows=[msg('hold','t1','USER','shared'),msg('hold','t2','SUBJECT','hidden'),
        msg('private','a1','USER','before'),msg('private','a2','USER','media'),msg('private','a3','SUBJECT','after'),
        msg('gap','b1','USER','before'),msg('gap','b2','SUBJECT','after','2026-01-01T10:00:00'),
        msg('ok','q','USER','a new context'),msg('ok','r','SUBJECT','first'),msg('ok','s','SUBJECT','part two'),msg('ok','n','USER','follow-up')]
  items,totals=extract(rows,[msg('hold','h','SUBJECT','hidden')],{'a2'},PROFILE)
  self.assertEqual([(i['id'],i['target'],i['next']) for i in items],[('r','first part two','follow-up')]);self.assertEqual(totals['discarded_shared_units'],1)
 def test_duplicated_id_blocks_even_if_text_changes(self):
  with self.assertRaisesRegex(ValueError,'cross-split'):
   extract([msg('train','collision','USER','old')],[msg('hold','collision','SUBJECT','new')],set(),PROFILE)
if __name__=='__main__':unittest.main()
