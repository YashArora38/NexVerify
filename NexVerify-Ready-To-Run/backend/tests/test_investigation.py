import pytest
from app.payment_intel import analyze_page_payments_and_links as scan
from app.proofgrid import evaluate, score_and_verdict
from app.investigation import investigate
from app.web import Page

@pytest.mark.parametrize('html,text', [
    ('<p>9876543210@paytm</p>', 'Pay via UPI 9876543210@paytm'),
    ('<form action="https://formspree.io/f/contact"><input name="message"></form>', 'Contact us'),
    ('<a href="https://bit.ly/abc">Help</a>', 'Our help page'),
    ('<form method="post" action="/login"><input type="password"></form>', 'Sign in'),
    ('<form method="post" action="https://checkout.stripe.com/pay"><input name="card_number"></form>', 'Checkout'),
])
def test_ordinary_business_not_penalized(html, text):
    assert not scan(html,text,'https://shop.example/')['risk_flags']

@pytest.mark.parametrize('value', ['person@gmail.com', 'help@company.com', 'user@paytm.com'])
def test_email_is_not_upi(value):
    assert not scan('',value,'https://shop.example/')['upi_ids']

@pytest.mark.parametrize('html', ['<p>checkout.razorpay.com</p>', '<script src="https://checkout.razorpay.com.evil.test/sdk.js"></script>', '<script src="https://evil.test/checkout.razorpay.com"></script>', '<a href="http://checkout.razorpay.com/pay">Pay</a>'])
def test_gateway_spoof_does_not_verify(html):
    assert not scan(html,'','https://shop.example/')['detected_gateways']

def test_real_gateway_reference_does_not_verify_merchant():
    r=scan('<script src="https://checkout.razorpay.com/v1/checkout.js"></script>','','https://shop.example/')
    assert r['detected_gateways'] == ['Razorpay'] and r['merchant_verified'] is False

@pytest.mark.parametrize('action,method,expected', [
    ('http://shop.example/login','post','INSECURE_SENSITIVE_FORM'),
    ('//collector.example.net/collect','post','SENSITIVE_EXTERNAL_FORM'),
    ('/login','get','SENSITIVE_QUERY_STRING'),
])
def test_sensitive_form_destinations(action, method, expected):
    r=scan(f'<form action="{action}" method="{method}"><input type="password"></form>','','https://shop.example/')
    assert expected in [f['rule'] for f in r['risk_flags']]

def test_download_and_encoded_script_are_observations():
    r=scan('<a href="/app.apk">Install</a><script>eval(atob("abc"))</script>','','https://shop.example/')
    assert r['downloads'][0]['url']=='https://shop.example/app.apk'
    assert r['downloads'][0]['status']=='link_only_not_downloaded'
    assert not r['risk_flags'] and any('JavaScript' in o for o in r['observations'])

def test_store_listing_alone_is_not_safety_proof():
    subject={'query':'Unknown App','display_name':'Unknown App','category':'general','app_store_url':'https://apps.apple.com/in/app/unknown/id12345'}
    outputs={'listing': {'status':'done','data':{'apple_verified':True}}}
    hits=evaluate(subject,outputs)
    assert score_and_verdict(hits,subject,outputs)[1]['code']=='UNKNOWN'

@pytest.mark.asyncio
async def test_bounded_crawl_preserves_evidence_and_avoids_mutations(tmp_path):
    from app.evidence import EvidenceStore
    class Context:
        demo=None
        evidence=EvidenceStore('crawl-test')
        calls=[]
        async def fetch(self,url):
            self.calls.append(url)
            return Page(url,url,200,'Contact','<form method="post" action="http://site.example/login"><input type="password"></form>','Contact')
    ctx=Context()
    html=''.join(f'<a href="/{p}">{p}</a>' for p in ['contact','privacy','about','refund','logout','payment?buy=1','app.apk'])+'<a href="https://other.example/contact">Other</a>'
    root=Page('https://site.example/','https://site.example/',200,'Home',html,'Home')
    data, ids=await investigate(ctx,root)
    assert len(ctx.calls)==3 and all('buy' not in u and 'logout' not in u for u in ctx.calls)
    assert data['coverage']['pages_read']==4 and len(ids)==4
    assert data['risk_flags'][0]['evidence_id'] in ids
    assert len(data['risk_flags']) == 1
