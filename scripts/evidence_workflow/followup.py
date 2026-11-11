"""Four alternating turns with leakage, speaker, PII, gap, and media boundaries. No network."""
import collections,datetime
from prepare import unsafe
def windows(source,forbidden,flags,gap=1800):
 ids=set();groups=collections.defaultdict(list)
 for r in source:
  if r['msgId'] in ids or r['msgId'] in forbidden[1]:raise ValueError('duplicate message or split overlap')
  ids.add(r['msgId']);key=r['textId'],r['convId']
  if key not in forbidden[0]:groups[key].append(r)
 for key,rr in groups.items():
  turns=[];prev=None
  for r in rr:
   t=r['text'].strip();stamp=datetime.datetime.fromisoformat(r['at']) if r.get('at') else None
   if stamp and prev and not 0 <= (stamp-prev).total_seconds()<=gap:turns.append(None)
   prev=stamp
   if not t or r['speaker'] not in ('USER','SUBJECT') or r['msgId'] in flags or unsafe.search(t):turns.append(None);continue
   if turns and turns[-1] and turns[-1][0]==r['speaker']:turns[-1][1].append(r)
   else:turns.append((r['speaker'],[r]))
  for i in range(3,len(turns)):
   four=turns[i-3:i+1]
   if not all(four) or [a[0] for a in four]!=['USER','SUBJECT']*2:continue
   yield {'unit':key,'id':four[-1][1][0]['msgId'],'ids':[r['msgId'] for _,z in four for r in z],
          'turns':[' '.join(r['text'].strip() for r in z) for _,z in four]}
def main():
 """Create separate local packets for input and observed response coders."""
 import argparse,json,os
 from pathlib import Path
 from prepare import read,rows
 p=argparse.ArgumentParser(description=main.__doc__);p.add_argument('--corpus',required=True);p.add_argument('--holdout',required=True);p.add_argument('--digest',required=True);p.add_argument('--private-dir',required=True);p.add_argument('--gap-seconds',type=int,default=1800)
 a=p.parse_args();d=Path(a.private_dir)
 if a.gap_seconds<=0:p.error('gap must be positive')
 if d.exists() and any(d.iterdir()):p.error('use a new empty private directory')
 d.mkdir(mode=0o700,parents=True,exist_ok=True)
 held=rows(a.holdout);denied=({(x['textId'],x['convId']) for x in held},{x['msgId'] for x in held})
 def opened(name):return os.fdopen(os.open(d/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'w',encoding='utf-8')
 with opened('친구조건.jsonl') as inp,opened('실제반응.jsonl') as out:
  for r in windows(rows(a.corpus),denied,{f['msgId'] for f in read(a.digest)['piiFlags']},a.gap_seconds):
   pre={k:r[k] for k in ['unit','id']};pre['turns']=r['turns'][:3]
   inp.write(json.dumps(pre,ensure_ascii=False)+'\n');out.write(json.dumps(r,ensure_ascii=False)+'\n')
if __name__=='__main__':main()
