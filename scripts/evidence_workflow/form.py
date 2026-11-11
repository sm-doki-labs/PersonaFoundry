"""Compile a reviewed card set. Optionally run an offline author and reviewer first.
Commands are JSON argv arrays; exchange one JSON document on stdin/stdout, no shell.
"""
import argparse,json,os,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
from prepare import read, write, run
HERE=Path(__file__).resolve().parent
def ask(cmd,instructions,payload):
 argv=json.loads(cmd)
 if not isinstance(argv,list) or not argv or not all(isinstance(s,str) and s for s in argv):raise ValueError('expected JSON argv array')
 env=dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
 proc=subprocess.run(argv,input=json.dumps({'instruction':instructions,'data':payload},ensure_ascii=False),text=True,capture_output=True,timeout=900,env=env)
 if proc.returncode:raise ValueError('local adapter failed; raw output suppressed')
 return json.loads(proc.stdout)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for k in ['corpus','holdout','digest','profile','facts','out','compiler']:p.add_argument('--'+k,required=True)
 for k in ['approved','author','reviewer','brief']:p.add_argument('--'+k)
 a=p.parse_args()
 auto=bool(a.author and a.reviewer and a.brief)
 if not ((auto and not a.approved) or (a.approved and not any([a.author,a.reviewer,a.brief]))):p.error('give --approved OR --author --reviewer --brief')
 out=Path(a.out)
 if out.exists() and any(out.iterdir()):p.error('--out must be empty; create a new revision')
 out.mkdir(parents=True,exist_ok=True)
 if auto:
  import tempfile
  with tempfile.TemporaryDirectory() as t:
   review=Path(t)/'private.json';run(SimpleNamespace(**{**vars(a),'review':str(review),'approved':None}))
   packet=read(review);brief=read(a.brief)
   cand=ask(a.author,(HERE/'추출지시문.md').read_text(),dict(brief=brief,stats=read(out/'분석.json'),records=packet))['sections']
   import importlib.util
   modspec=importlib.util.spec_from_file_location('reviewed_compiler',a.compiler)
   module=importlib.util.module_from_spec(modspec);modspec.loader.exec_module(module)
   # The mechanical gate precedes and cannot be overruled by the semantic reviewer.
   by={r['id']:r for r in packet}; valid=[]; holds=[]
   for n,c in enumerate(cand):
    try:
     module.compile_prompt(dict(role=brief['role'],scene=brief['scene'],facts=Path(a.facts).read_text(),sections=[c],trainIds=list(by),holdoutIds=[]))
     if len({tuple(by[i]['unit']) for i in c['evidence']})<2:raise ValueError('single source unit')
     valid.append(c)
    except (KeyError,TypeError,ValueError):holds.append({'candidateIndex':n,'decision':'hold','reason':'형식·예시·독립 근거 검사 미충족'})
   write(out/'선행보류.json',holds)
   if not valid:raise ValueError('no valid candidates after structural review; hold release')
   cand=valid
   allowed={r['id'] for r in packet}
   if not all(isinstance(c.get('evidence'),list) and set(c['evidence'])<=allowed for c in cand):raise ValueError('author used unknown reference')
   dec=[]
   for n,c in enumerate(cand):
    # One transport call per card: positional mistakes cannot approve the wrong rule.
    audit=ask(a.reviewer,(HERE/'검토지시문.md').read_text(),dict(brief=brief,records=[by[i] for i in c['evidence']],counterpoints=[r for r in packet if r['id'] not in c['evidence']][:8],candidate=c))
    verdict=audit.get('decision');reason=audit.get('reason')
    if verdict not in ('accept','hold') or not isinstance(reason,str) or not reason.strip():verdict,reason='hold','검토자가 유효한 결정을 반환하지 않았다.'
    dec.append(dict(index=n,decision=verdict,reason=reason))
   write(out/'검토결정.json',dec)
   if not any(d['decision']=='accept' for d in dec):raise ValueError('no accepted evidence; hold release')
   selected=[cand[d['index']] for d in sorted(dec,key=lambda x:x['index']) if d['decision']=='accept']
   a.approved=str(Path(t)/'candidate.json');write(a.approved,dict(role=brief['role'],scene=brief['scene'],sections=selected))
   run(SimpleNamespace(**vars(a),review=None))
   write(out/'승인카드.json',read(a.approved))
 else:run(SimpleNamespace(**vars(a),review=None))
 subprocess.run([sys.executable,a.compiler,str(out/'승인입력.json'),str(out/'최종프롬프트.md')],check=True)
if __name__=='__main__':main()
