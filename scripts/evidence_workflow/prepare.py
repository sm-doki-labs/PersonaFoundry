"""Offline, speaker-aligned S0 -> review -> compiler input. No network/dependencies.
See 공정.md for commands. Source format follows the intake stage (UTF-8 JSONL).
"""
import argparse, collections, datetime, hashlib, itertools, json, random, re, statistics
from pathlib import Path
def read(p):return json.loads(Path(p).read_text())
def rows(p):return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]
def key(r):return (r['textId'], r['convId'])
def write(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def digest(x):return hashlib.sha256(x.encode()).hexdigest()
# Discard contact/payment/media messages and break the conversational sequence there.
unsafe=re.compile(r'https?://|[\w.+-]+@[\w.-]+\.\w+|\d{2,3}-\d{3,4}-\d{4}|송금(?:\s*받기|\s*요청)|원을 (?:보냈어요|받았어요)|^샵검색:|^(?:사진(?: \d+장)?|이모티콘|동영상|삭제된 메시지입니다\.)$')
FACT_BOUNDARY='사실표 또는 현재 대화에서 확인할 수 없는 개인사나 공동 기억은 긍정도 부정도 단정하지 않는다. 다른 일화로 메우지 않고, 지금 고를 수 있는 것만 현재 판단으로 답한다.'
def extract(train,hold,flags,profile):
 hkeys={key(r) for r in hold};hids={r['msgId'] for r in hold}; seen=set();items=[];bad=0
 if not hids or len(hids)!=len(hold):raise ValueError('missing or duplicate holdout IDs')
 groups=collections.defaultdict(list)
 for r in train:
  m=r['msgId']
  if m in seen or m in hids:raise ValueError('duplicate or cross-split message ID: '+m)
  seen.add(m)
  if key(r) not in hkeys:groups[key(r)].append(r)
 patterns=[(k,re.compile(v)) for k,v in profile['input_patterns']]
 for group,rr in groups.items():
  turns=[];prev=None
  for r in rr:
   t=r['text'].strip();stamp=datetime.datetime.fromisoformat(r['at']) if r.get('at') else None
   if prev and stamp and not 0 <= (stamp-prev).total_seconds()<=profile['max_gap_seconds']:turns.append(None)
   prev=stamp
   if not t or r['speaker'] not in ('USER','SUBJECT') or r['msgId'] in flags or unsafe.search(t):
    bad+=1;turns.append(None);continue
   if turns and turns[-1] and turns[-1][0]==r['speaker']:turns[-1][1].append(r)
   else:turns.append((r['speaker'],[r]))
  def as_text(b):return ' '.join(x['text'].strip() for x in b[1])
  for n in range(1,len(turns)):
   b=turns[n];a=turns[n-1]
   if not b or not a or b[0]!='SUBJECT' or a[0]!='USER':continue
   q=as_text(a);t=as_text(b);label=next((k for k,pat in patterns if pat.search(q)),'기타')
   nxt=turns[n+1] if n+1<len(turns) else None
   items.append(dict(id=b[1][0]['msgId'],unit=list(group),context=q,target=t,next=(as_text(nxt) if nxt and nxt[0]=='USER' else None),label=label))
 return items,dict(eligible_turns=len(items),eligible_units=len({tuple(x['unit']) for x in items}),discarded_shared_units=len(hkeys&{key(r) for r in train}),discarded_messages=bad,holdout_units=len(hkeys),holdout_messages=len(hids))
def stats(items):
 t=[x['target'] for x in items];return dict(n=len(t),units=len({tuple(x['unit']) for x in items}),median_chars=statistics.median(map(len,t)),laugh=sum(bool(re.search(r'[ㅋㅎ]{2,}',s)) for s in t),qmark=sum('?' in s for s in t),at_most_10=sum(len(s)<=10 for s in t))
def run(a):
 profile=read(a.profile);train=rows(a.corpus);hold=rows(a.holdout);flags={r['msgId'] for r in read(a.digest)['piiFlags']}
 items,totals=extract(train,hold,flags,profile)
 if not items:raise ValueError('no eligible turns')
 by={i['id']:i for i in items};hids=sorted({r['msgId'] for r in hold});out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
 buckets=collections.defaultdict(list)
 for i in items:buckets[i['label']].append(i)
 audit={'selection':totals,'train':stats(items),'labels':{k:stats(v) for k,v in buckets.items()},'idsSha256':digest('\n'.join(sorted(by)))}
 write(out/'분석.json',audit)
 if a.review:
  # This optional packet contains private text and is deliberately not a release artifact.
  rnd=random.Random(811);packet=[]
  for k,rs in sorted(buckets.items()):
   local=rs.copy();rnd.shuffle(local);count=collections.Counter()
   for r in local:
    u=tuple(r['unit'])
    if count[u]>=2:continue
    count[u]+=1;packet.append(r)
    if sum(count.values())>=profile['review_per_class']:break
  write(a.review,packet)
 if a.approved:
  spec=read(a.approved);facts=Path(a.facts).read_text();cards=spec['sections'];trace=[]
  if not cards:raise ValueError('no approved cards; hold release')
  for c in cards:
   evidence=[by[k] for k in c['evidence']]
   units={tuple(r['unit']) for r in evidence}
   if len(units)<2:raise ValueError('unreplicated tendency; hold or request another source')
   if len(set(c['evidence']))!=len(evidence):raise ValueError('duplicate evidence')
   compact=lambda s:re.sub(r'\s+','',s)
   line=compact(c['rule'])
   for r in evidence:
    if any(line[j:j+12] in compact(r[k]) for j in range(max(0,len(line)-11)) for k in ('target','context')):raise ValueError('copied utterance span')
   trace.append({'section':c['section'],'evidence':c['evidence'],'units':len(units),'ruleSHA256':digest(c['rule'])})
  role=spec['role'] if FACT_BOUNDARY in spec['role'] else spec['role'].rstrip()+' '+FACT_BOUNDARY
  write(out/'승인입력.json',dict(role=role,scene=spec['scene'],facts=facts,sections=cards,trainIds=sorted(by),holdoutIds=hids))
  write(out/'근거검사.json',{'factsSHA256':digest(facts),'rules':trace,'empty_sections':sorted(set('LIFE_AND_TASTES DISPOSITION WANTS_AND_FEARS READING_AND_TENSION CHOICES VOICE KNOWS_AND_LIMITS'.split())-{c['section'] for c in cards})})
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for k in ('corpus','holdout','digest','profile','out'):p.add_argument('--'+k,required=True)
 for k in ('review','approved','facts'):p.add_argument('--'+k)
 a=p.parse_args()
 if bool(a.approved)!=bool(a.facts):p.error('--approved and --facts must be supplied together')
 run(a)
