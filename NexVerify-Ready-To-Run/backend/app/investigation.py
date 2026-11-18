"""Bounded, read-only investigation of public page surfaces."""
import asyncio
from urllib.parse import urlparse, urldefrag
from .payment_intel import SurfaceParser, analyze_page_payments_and_links
from .evidence import utc_now

async def investigate(ctx, root):
    base = root.final_url or root.url
    parser = SurfaceParser(base)
    parser.feed(root.html[:2_000_000])
    candidates = []
    for raw in parser.links:
        url = urldefrag(raw)[0]
        p = urlparse(url)
        # Only public informational pages: never submit checkout, credentials or payments.
        segments = set(p.path.lower().strip('/').split('/'))
        if (p.scheme in ('https', 'http') and p.netloc == urlparse(base).netloc and not p.query
                and segments & {'about', 'about-us', 'contact', 'contact-us', 'privacy', 'privacy-policy', 'refund', 'refund-policy', 'download', 'downloads', 'payment', 'payments'}
                and not segments & {'logout', 'delete', 'pay', 'buy', 'submit', 'unsubscribe'}
                and url != base and url not in candidates):
            candidates.append(url)
    async def fetch(url):
        try: return await asyncio.wait_for(ctx.fetch(url), timeout=7)
        except Exception: return None
    children = await asyncio.gather(*(fetch(u) for u in candidates[:3]))
    pages, inspections, evidence_ids = [], [], []
    for url, page in [(base, root)] + list(zip(candidates[:3], children)):
        record = {'url': url, 'final_url': page.final_url if page else url, 'http_status': page.status if page else 0, 'status': 'read' if page and page.ok else 'unavailable', 'redirect_chain': getattr(page, 'redirect_chain', []) if page else []}
        if page and page.ok:
            ev = ctx.evidence.add('listing', 'surface', 'Public HTML surface and redirects', page.final_url, {'url': page.final_url, 'html': page.html[:2_000_000], 'redirect_chain': getattr(page, 'redirect_chain', [])}, simulated=ctx.demo is not None)
            evidence_ids.append(ev['id'])
            record['evidence_id'] = ev['id']
            inspection = analyze_page_payments_and_links(page.html, page.text, page.final_url or url)
            inspection['evidence_id'] = ev['id']
            inspections.append(inspection)
        pages.append(record)
    merged = dict(inspections[0]) if inspections else analyze_page_payments_and_links('', '', base)
    for key in ('upi_ids', 'phone_vpas', 'detected_gateways', 'gateway_references', 'shortened_links', 'external_forms', 'whatsapp_redirects', 'telegram_redirects', 'forms', 'downloads', 'script_sources', 'declared_redirects', 'content_indicators', 'observations'):
        merged[key] = []
        for inspection in inspections:
            for item in inspection[key]:
                if item not in merged[key]: merged[key].append(item)
    merged['risk_flags'] = []
    seen = set()
    for inspection in inspections:
        for flag in inspection['risk_flags']:
            if flag['rule'] not in seen:
                merged['risk_flags'].append({**flag, 'source_url': inspection['page_url'], 'evidence_id': inspection['evidence_id']})
                seen.add(flag['rule'])
    merged['has_merchant_gateway'] = bool(merged['detected_gateways'])
    merged['merchant_verified'] = False
    merged['coverage'] = {'pages_read': sum(p['status'] == 'read' for p in pages), 'pages_attempted': len(pages), 'limit': 4, 'additional_candidates': max(0, len(candidates) - 3)}
    merged['pages'] = pages
    merged['captured_at'] = utc_now()
    merged['limitations'] = ['Public HTML and HTTP redirects only; server-side code and authenticated checkout are not accessible.', 'No payment, form submission, account login, installer execution or binary reverse engineering performed.', 'Domain registration dates identify domain creation, not app release dates or the identity of the operator.', 'Store listings, HTTPS, UPI and payment gateway references do not certify safety. Content categories are indicators, not findings of fraud.']
    return merged, evidence_ids
