"""Public HTML inspection. Observations are not merchant or malware certification."""
from __future__ import annotations
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, parse_qs

GATEWAYS = {
    'Razorpay': ('checkout.razorpay.com', 'api.razorpay.com', 'rzp.io'),
    'Cashfree': ('sdk.cashfree.com', 'payments.cashfree.com'),
    'PayU': ('secure.payu.in', 'test.payu.in'),
    'Paytm Merchant': ('securegw.paytm.in',),
    'PhonePe Merchant': ('mercury.phonepe.com', 'merchants.phonepe.com'),
    'CCAvenue': ('secure.ccavenue.com',), 'BillDesk': ('pgi.billdesk.com',),
    'Stripe': ('js.stripe.com', 'checkout.stripe.com'),
}
SHORTENERS = {'bit.ly', 'tinyurl.com', 'cutt.ly', 'is.gd', 'rb.gy', 't.co', 'shorturl.at'}
UPI = re.compile(r'(?<![\w.+-])([\w.-]{2,49}@(okhdfcbank|okaxis|oksbi|okicici|paytm|ybl|ibl|axl|upi|apl|postbank|federal|icici|sbi|hdfc|kotak|barodampay|pnb|indus|yesbank|aubank|fbl|idfcbank|freecharge|airtel|gpay))(?![\w.-])', re.I)
SENSITIVE = re.compile(r'password|passwd|otp|pin|cvv|cvc|card.?number|account.?number|aadhaar|aadhar', re.I)

class SurfaceParser(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.links, self.resources, self.forms, self.redirects = base, [], [], [], []
        self.current = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'base' and a.get('href'):
            self.base = urljoin(self.base, a['href'])
        if tag == 'a' and a.get('href'):
            self.links.append(urljoin(self.base, a['href']))
        if tag in ('script', 'iframe') and a.get('src'):
            self.resources.append({'kind': tag, 'url': urljoin(self.base, a['src'])})
        if tag == 'meta' and a.get('http-equiv', '').lower() == 'refresh':
            m = re.search(r'url\s*=\s*[\"\x27]?(.*?)[\"\x27]?$', a.get('content', ''), re.I)
            if m: self.redirects.append(urljoin(self.base, m[1]))
        if tag == 'form':
            self.current = {'action': urljoin(self.base, a.get('action') or self.base), 'method': a.get('method', 'get').upper(), 'sensitive_fields': []}
            self.forms.append(self.current)
        if tag == 'input' and self.current is not None:
            descriptor = ' '.join(a.get(k, '') for k in ('name', 'id', 'type', 'autocomplete'))
            if SENSITIVE.search(descriptor): self.current['sensitive_fields'].append(descriptor[:120])
    def handle_endtag(self, tag):
        if tag == 'form': self.current = None

def gateway_for(url):
    try:
        p = urlparse(url)
        if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443): return None
        host = (p.hostname or '').lower()
        return next((name for name, hosts in GATEWAYS.items() if host in hosts), None)
    except ValueError:
        return None

def analyze_page_payments_and_links(html: str, text: str, page_url: str = '') -> dict:
    parser = SurfaceParser(page_url)
    parser.feed((html or '')[:2_000_000])
    links = list(dict.fromkeys(parser.links))[:200]
    combined = (text or '') + '\n' + (html or '')
    upis = list(dict.fromkeys(m[0] for m in UPI.findall(combined)))
    for link in links:
        p = urlparse(link)
        if p.scheme == 'upi' and p.netloc == 'pay':
            for vpa in parse_qs(p.query).get('pa', []):
                if re.fullmatch(r'[\w.-]{2,49}@[\w.-]{2,30}', vpa) and vpa not in upis: upis.append(vpa)
    destinations = list(dict.fromkeys(links + [r['url'] for r in parser.resources] + [f['action'] for f in parser.forms]))
    gateways = [{'provider': gateway_for(u), 'url': u} for u in destinations if gateway_for(u)]
    host = (urlparse(page_url).hostname or '').lower()
    from .web import registrable_domain
    origin = registrable_domain(host)
    flags, observations = [], []
    def flag(rule, points, label, message):
        if not any(f['rule'] == rule for f in flags):
            flags.append({'rule': rule, 'points': points, 'label': label, 'en': message, 'hi': message})
    external_forms = []
    for form in parser.forms:
        dest = urlparse(form['action'])
        external = bool(dest.hostname and registrable_domain(dest.hostname) != origin)
        form['external'] = external
        form['gateway_provider'] = gateway_for(form['action'])
        if external: external_forms.append(form['action'])
        if form['sensitive_fields']:
            if dest.scheme == 'http':
                flag('INSECURE_SENSITIVE_FORM', 60, 'UNENCRYPTED DATA', 'A sensitive-data form submits over unencrypted HTTP: ' + form['action'])
            elif dest.scheme in ('http', 'https') and external and not form['gateway_provider']:
                flag('SENSITIVE_EXTERNAL_FORM', 35, 'CHECK DATA RECIPIENT', 'Sensitive fields submit to another domain; affiliation is unverified: ' + form['action'])
            if form['method'] == 'GET':
                flag('SENSITIVE_QUERY_STRING', 35, 'DATA IN URL', 'A sensitive form uses GET, which can expose entered values in URLs and logs: ' + form['action'])
    downloads = [{'url': u, 'host': urlparse(u).hostname, 'type': urlparse(u).path.rsplit('.', 1)[-1].lower(), 'status': 'link_only_not_downloaded'} for u in links if re.search(r'\.(apk|xapk|apks|ipa|exe|msi|dmg|mobileconfig)$', urlparse(u).path, re.I)]
    short = [u for u in links if urlparse(u).hostname in SHORTENERS]
    phones = [u for u in upis if re.fullmatch(r'[6-9]\d{9}@.+', u)]
    if upis: observations.append('UPI handles observed. Handle format does not establish merchant identity or fraud; confirm the recipient in your payment app.')
    if gateways: observations.append('Recognized HTTPS gateway endpoint referenced. Merchant onboarding, recipient identity and transaction safety have not been verified.')
    if external_forms: observations.append('External forms can be legitimate payment, login or support integrations. Sensitive destinations need independent verification.')
    if short: observations.append('Shortened links observed; destination is not inferred from the shortener alone.')
    if downloads: observations.append('Direct installers found. No binary was downloaded, executed, decompiled or malware-scanned; store absence alone is not fraud.')
    if re.search(r'\b(?:eval\s*\(\s*atob|new\s+Function\s*\(|document\.write\s*\(\s*unescape)', html or '', re.I):
        observations.append('Encoded or dynamically constructed JavaScript pattern observed. This heuristic alone does not prove malicious execution.')
    categories = []
    for category, pattern in [('betting', r'place\s+(?:a\s+)?bet|sportsbook|online\s+casino'), ('adult', r'\bxxx\b|pornographic|adult\s+videos'), ('credential theft claims', r'password\s+stealer|steal\s+credentials')]:
        if re.search(pattern, text or '', re.I): categories.append(category)
    return {'upi_ids': upis[:40], 'phone_vpas': phones[:40], 'detected_gateways': list(dict.fromkeys(g['provider'] for g in gateways)), 'gateway_references': gateways[:30], 'has_merchant_gateway': bool(gateways), 'merchant_verified': False, 'asks_direct_payment': bool(re.search(r'pay\s+(?:via\s+)?upi|scan\s+and\s+pay|send\s+money', text or '', re.I)), 'has_p2p_upi': False, 'shortened_links': short, 'external_forms': external_forms, 'whatsapp_redirects': [u for u in links if urlparse(u).hostname in ('wa.me', 'api.whatsapp.com')], 'telegram_redirects': [u for u in links if urlparse(u).hostname in ('t.me', 'telegram.me')], 'risk_flags': flags, 'forms': parser.forms[:40], 'downloads': downloads[:40], 'script_sources': parser.resources[:40], 'declared_redirects': parser.redirects[:20], 'content_indicators': categories, 'observations': observations, 'page_url': page_url}
