"""Human-readable investigation export, shared by PDF and text endpoints."""
def investigation_lines(result):
    data = result.get('investigation') or {}
    coverage = data.get('coverage') or {}
    lines = [f"Public pages read: {coverage.get('pages_read', 0)} / {coverage.get('pages_attempted', 0)} attempted (maximum 4)."]
    for page in data.get('pages', []):
        lines.append(f"{page['status'].upper()} | {page['url']} -> {page['final_url']} | HTTP {page['http_status']} | Evidence {page.get('evidence_id', 'none')}")
        for hop in page.get('redirect_chain', []):
            lines.append(f"  HTTP redirect trace: {hop.get('status')} {hop.get('url')}")
    for key, title in [('upi_ids', 'UPI handle'), ('content_indicators', 'Content indicator'), ('observations', 'Observation')]:
        for value in data.get(key, []): lines.append(f'{title}: {value}')
    for item in data.get('gateway_references', []):
        lines.append(f"Gateway reference: {item['provider']} | {item['url']} | Merchant NOT verified")
    for item in data.get('forms', []):
        lines.append(f"Form destination: {item['method']} {item['action']} | Sensitive fields: {', '.join(item['sensitive_fields']) or 'none detected'}")
    for item in data.get('downloads', []):
        lines.append(f"Installer link: {item['url']} | {item['type']} | Binary not analyzed")
    for item in data.get('script_sources', []):
        lines.append(f"{item['kind']} reference: {item['url']} | Content not executed or fetched separately")
    for item in data.get('declared_redirects', []): lines.append('Declared HTML redirect (not followed): ' + item)
    for value in data.get('limitations', []): lines.append('Scope: ' + value)
    return lines

def build_text_report(result):
    lines = ['NEXVERIFY | PUBLIC EVIDENCE REPORT', 'DEMO: simulated evidence, not a real allegation' if result.get('demo') else 'Live public-source assessment', f"Check: {result['check_id']} | Captured: {result['started_at']}", f"Subject: {result['query']}", f"Verdict: {result['verdict']['label_en']} | Score: {'unknown' if result['verdict']['code'] == 'UNKNOWN' else result['score']}", 'An assessment is not proof of fraud, safety, operator identity or legal admissibility.', '', 'SCORE DEDUCTIONS']
    for hit in result['hits']:
        lines.append(f"-{hit['penalty']} | {hit['rule_id']} | {hit['found']} | Evidence: {', '.join(hit['evidence_ids']) or 'see source method'}")
    if not result['hits']: lines.append('No scoring rules triggered; missing evidence does not establish safety.')
    lines += ['', 'PUBLIC SURFACE INVESTIGATION', *investigation_lines(result), '', 'EVIDENCE MANIFEST', result['manifest_sha256']]
    for ev in result['evidence']: lines.append(f"{ev['id']} | {ev.get('source_url') or ev['label']} | {ev['captured_at']} | SHA-256 {ev['sha256']}")
    lines += ['', 'COMPLAINT DRAFT - REVIEW BEFORE SUBMISSION', result['complaint_text']]
    return '\n'.join(lines)
