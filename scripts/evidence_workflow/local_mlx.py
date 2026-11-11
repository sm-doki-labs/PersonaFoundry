"""Optional adapter: local MLX model directory, offline, one JSON object via stdio.
Use a network-denied launcher for private data. pip dependency: mlx-lm (Apple Silicon).
"""
import argparse, json, os, re, sys
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('model_dir',type=Path);p.add_argument('--limit',type=int,default=3);p.add_argument('--max-tokens',type=int,default=1600);a=p.parse_args()
 if not a.model_dir.is_dir():p.error('model_dir must already exist locally')
 os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
 from mlx_lm import load,generate
 from mlx_lm.sample_utils import make_sampler
 req=json.load(sys.stdin)
 m,t=load(str(a.model_dir.resolve()),tokenizer_config={'local_files_only':True})
 msg=[{'role':'system','content':req['instruction']+('\n첫 후보 '+str(a.limit)+'개 이내로 제한한다.' if 'candidate' not in req['data'] else '')+' ID를 창작하지 않는다. 순수 JSON 하나만 출력한다.'},{'role':'user','content':json.dumps(req['data'],ensure_ascii=False)}]
 reply=generate(m,t,prompt=t.apply_chat_template(msg,tokenize=True,add_generation_prompt=True,return_dict=False),sampler=make_sampler(temp=0),max_tokens=a.max_tokens,verbose=False).strip()
 reply=re.sub(r'^\x60\x60\x60(?:json)?\s*|\s*\x60\x60\x60$','',reply).strip();obj=json.loads(reply)
 json.dump(obj,sys.stdout,ensure_ascii=False)
if __name__=='__main__':main()
