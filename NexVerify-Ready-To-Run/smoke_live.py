import httpx,json
with httpx.Client(base_url='http://127.0.0.1:3000',timeout=100,headers={'Origin':'http://127.0.0.1:3000'}) as c:
 cid=c.post('/api/check',json={'query':'https://sbi.bank.in','fresh':True}).json()['check_id']
 c.get(f'/api/check/{cid}/stream')
 r=c.get(f'/api/check/{cid}').json()
 print(json.dumps({'check_id':cid,'verdict':r['verdict']['code'],'score':r['score'],'coverage':r.get('investigation',{}).get('coverage'),'partial':r['partial'],'unverified':r['unverified']}))
