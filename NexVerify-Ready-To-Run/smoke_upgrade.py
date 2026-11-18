from pathlib import Path
import httpx, json
root=Path(__file__).resolve().parent
out=root/'output'/'verification';out.mkdir(parents=True,exist_ok=True)
with httpx.Client(base_url='http://127.0.0.1:3000',timeout=100,headers={'Origin':'http://127.0.0.1:3000'}) as c:
    assert c.get('/api/health').json()['ok']
    cid=c.post('/api/check',json={'query':'QuickRupee','fresh':True}).json()['check_id']
    stream=c.get(f'/api/check/{cid}/stream');assert 'event: result' in stream.text
    result=c.get(f'/api/check/{cid}').json()
    assert result['engine']=='proofgrid-3'
    assert result['investigation']['downloads'] and not result['investigation']['detected_gateways']
    assert any(h['rule_id']=='INSECURE_SENSITIVE_FORM' for h in result['hits'])
    for ext in ['pdf','txt']:
        response=c.get(f'/api/check/{cid}/report.{ext}');assert response.status_code==200
        (out/f'QuickRupee-DEMO.{ext}').write_bytes(response.content)
    assert c.get(f'/api/check/{cid}/verify').json()['ok']
    z=c.get(f'/api/check/{cid}/bundle.zip');assert z.content.startswith(b'PK')
    (out/'smoke-result.json').write_text(json.dumps({'check_id':cid,'engine':result['engine'],'verdict':result['verdict']['code'],'pages':result['investigation']['coverage'],'report':str(out/'QuickRupee-DEMO.pdf')},indent=2))
    print((out/'smoke-result.json').read_text())
