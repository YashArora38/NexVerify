"""Compile the 1-click evidence PDF (Capture -> Seal -> Compile -> File)."""
from __future__ import annotations

import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from . import config

NAVY = colors.HexColor("#1F3A68")
BLUE = colors.HexColor("#2F5597")
RED = colors.HexColor("#C00000")
AMBER = colors.HexColor("#B8860B")
GREEN = colors.HexColor("#3B7D23")
GRAY = colors.HexColor("#6B7280")
LIGHT = colors.HexColor("#EEF2F8")
COLOR = {"red": RED, "amber": AMBER, "green": GREEN, "gray": GRAY}

_ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_ss["Heading1"], textColor=NAVY, fontSize=18, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=_ss["Heading2"], textColor=NAVY, fontSize=13, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("body", parent=_ss["BodyText"], fontSize=9.5, leading=13)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10.5, textColor=GRAY)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.5, leading=11)
CELLB = ParagraphStyle("cellb", parent=CELL, fontName="Helvetica-Bold")
HEADC = ParagraphStyle("headc", parent=CELL, textColor=colors.white, fontName="Helvetica-Bold")
MONO = ParagraphStyle("mono", fontName="Courier", fontSize=7.2, leading=9)
SCORE = ParagraphStyle("score", parent=BODY, fontSize=34, leading=38, alignment=TA_CENTER, fontName="Helvetica-Bold")


def _p(text, style=CELL):
    return Paragraph(escape(str(text or "")), style)


def _ascii(s: str) -> str:
    """Built-in PDF fonts have no Devanagari / rupee glyphs."""
    return (s or "").replace("₹", "Rs.").replace("→", "->").encode("cp1252", "replace").decode("cp1252")


def _wrap(text: str, width: int = 105, max_lines: int = 70) -> str:
    out = []
    for line in _ascii(text).splitlines():
        out.extend(textwrap.wrap(line, width) or [""])
        if len(out) >= max_lines:
            out = out[:max_lines] + ["... (trimmed; full file is in the evidence folder, hash above)"]
            break
    return "\n".join(out)


def build_pdf(result: dict) -> Path:
    out_path = config.REPORT_DIR / f"{result['check_id']}.pdf"
    s = result["subject"]
    v = result["verdict"]
    vcolor = COLOR.get(v["color"], GRAY)

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1] - 14 * mm, A4[0], 14 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(15 * mm, A4[1] - 9 * mm, "NexVerify  |  Evidence Report")
        canvas.setFont("Helvetica", 8.5)
        canvas.drawRightString(A4[0] - 15 * mm, A4[1] - 9 * mm,
                               f"Check {result['check_id']}" + ("   DEMO DATA (MADE UP)" if result.get("demo") else ""))
        canvas.setFillColor(GRAY)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(15 * mm, 9 * mm, "Automated check of public records. Not legal advice. "
                                           "File complaints yourself at cybercrime.gov.in or call 1930.")
        canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=20 * mm, bottomMargin=16 * mm,
                            title=f"NexVerify report - {s.get('display_name')}", author="NexVerify")
    st: list = []

    st.append(Paragraph(escape(_ascii(f"Check: {s.get('display_name')}")), H1))
    st.append(Paragraph(f"Checked {escape(result['started_at'])} UTC &middot; took "
                        f"{result['duration_ms'] / 1000:.1f}s &middot; manifest SHA-256 "
                        f"<font face='Courier'>{result['manifest_sha256'][:24]}...</font>", SMALL))
    if result.get("demo"):
        st.append(Paragraph("<b>Demo data:</b> every name, link, number and report in this file is made up.", SMALL))
    st.append(Spacer(1, 6))

    # --- score box ----------------------------------------------------------
    shown = "?" if v["code"] == "UNKNOWN" else result["score"]
    score_cell = [Paragraph(f"<font color='{vcolor.hexval()}'>{shown}</font>"
                            f"<font size='14' color='{vcolor.hexval()}'>/100</font>", SCORE)]
    verdict_cell = [Paragraph(f"<font color='{vcolor.hexval()}'><b>{escape(v['label_en'])}</b></font>",
                              ParagraphStyle("v", parent=BODY, fontSize=13, leading=16)),
                    Spacer(1, 3), _p(_ascii(result["summary"]["en"]), BODY)]
    if result.get("partial"):
        verdict_cell.append(_p("Partial score: could not check " + ", ".join(result["unverified"]) +
                               ". Those sources gave no penalty.", SMALL))
    t = Table([[score_cell, verdict_cell]], colWidths=[45 * mm, 135 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("BOX", (0, 0), (-1, -1), 0.6, vcolor), ("TOPPADDING", (0, 0), (-1, -1), 8),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    st.append(t)

    # --- human assist notice if applicable ---
    if result.get("human_assisted"):
        st.append(Spacer(1, 4))
        ha_banner = Table([[_p("<b>HUMAN-ASSISTED REPORT:</b> Analysis includes evidence provided directly by user (screenshot / page text / questionnaire responses).", ParagraphStyle("ha", parent=BODY, textColor=NAVY))]],
                          colWidths=[180 * mm])
        ha_banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF8E7")),
                                      ("BOX", (0, 0), (-1, -1), 0.8, AMBER), ("PADDING", (0, 0), (-1, -1), 6)]))
        st.append(ha_banner)

    # --- Score Breakdown Table -----------------------------------------------
    breakdown = result.get("score_breakdown") or []
    if breakdown:
        st.append(Paragraph("Transparent Score Breakdown & Checklist", H2))
        b_rows = [[_p("Signal", HEADC), _p("Status", HEADC), _p("Evidence Found", HEADC), _p("Source", HEADC), _p("Pts", HEADC)]]
        for b in breakdown:
            st_col = GREEN if b["status"] == "pass" else RED if b["status"] == "fail" else AMBER if b["status"] == "warn" else GRAY
            b_rows.append([
                _p(_ascii(b["title_en"]), CELLB),
                Paragraph(f"<font color='{st_col.hexval()}'><b>{escape(b['status'].upper())}</b></font>", CELL),
                _p(_ascii(b["evidence_en"])),
                _p(_ascii(b["source"])),
                _p(_ascii(b["points"]))
            ])
        bt = Table(b_rows, colWidths=[38 * mm, 20 * mm, 74 * mm, 36 * mm, 12 * mm], repeatRows=1)
        bt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE), ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                                ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        st.append(bt)

    # Public surface investigation is shared with the downloadable text report.
    from .report_text import investigation_lines
    if result.get("investigation"):
        st.append(Paragraph("Payment, download and website investigation", H2))
        for line in investigation_lines(result):
            st.append(_p(_ascii(line), SMALL))
            st.append(Spacer(1, 3))

    # --- subject ------------------------------------------------------------
    st.append(Paragraph("What was checked", H2))
    rows = [["Name", s.get("display_name")], ["Category", s.get("category")],
            ["Website", s.get("website_url")], ["Google Play", s.get("play_url")], ["Apple App Store", s.get("app_store_url")],
            ["Telegram", s.get("telegram_url")], ["Legal name", s.get("legal_name")]]
    rows = [[_p(a, CELLB), _p(_ascii(b))] for a, b in rows if b]
    t = Table(rows, colWidths=[30 * mm, 150 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    st.append(t)

    # --- ProofGrid ------------------------------------------------------------
    st.append(Paragraph("ProofGrid: what they claim vs what records show", H2))
    hits = sorted(result["hits"], key=lambda h: -h["penalty"])
    if hits:
        rows = [[_p("What they claim", HEADC), _p("How we checked", HEADC), _p("What we found", HEADC),
                 _p("Penalty", HEADC), _p("Proof", HEADC)]]
        for h in hits:
            rows.append([_p(_ascii(h["claim"])), _p(_ascii(h["how_checked"])), _p(_ascii(h["found"])),
                         Paragraph(f"<font color='{RED.hexval()}'><b>-{h['penalty']}</b></font>", CELL),
                         _p(", ".join(h["evidence_ids"]))])
        t = Table(rows, colWidths=[42 * mm, 44 * mm, 58 * mm, 16 * mm, 20 * mm], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE), ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        st.append(t)
    else:
        st.append(_p("No rule fired. No contradictions found in the records checked.", BODY))
    st.append(Spacer(1, 4))
    st.append(_p("Score is unknown because identity evidence is insufficient; the internal neutral value is not a safety rating." if v["code"] == "UNKNOWN" else f"score = max(0, 100 - {result['total_penalty']}) = {result['score']}", BODY))

    # --- sources --------------------------------------------------------------
    st.append(Paragraph("Five checks", H2))
    rows = [[_p("Source", HEADC), _p("Result", HEADC), _p("Detail", HEADC), _p("Method", HEADC), _p("Pts", HEADC)]]
    for c in result["cards"]:
        col = COLOR.get(c["color"], GRAY)
        rows.append([_p(c["title"], CELLB),
                     Paragraph(f"<font color='{col.hexval()}'><b>{escape(c['label'] or c['state'].upper())}</b></font>", CELL),
                     _p(_ascii(c["detail_en"])), _p(c.get("method", "")), _p(str(c["penalty"]))])
    t = Table(rows, colWidths=[38 * mm, 26 * mm, 62 * mm, 40 * mm, 14 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE), ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    st.append(t)

    # --- complaint --------------------------------------------------------------
    st.append(Paragraph("Ready-to-file complaint (cybercrime.gov.in / 1930)", H2))
    st.append(_p("1) Go to cybercrime.gov.in and choose 'Report Cyber Crime' -> Financial Fraud. "
                 "2) Log in with your own mobile number and OTP. 3) Paste the text below and fill the blanks. "
                 "4) Attach this PDF. If you lost money, call 1930 as fast as possible.", BODY))
    st.append(Spacer(1, 4))
    for line in result["complaint_text"].splitlines():
        st.append(_p(_ascii(line), SMALL) if line else Spacer(1, 5))

    # --- evidence pages ---------------------------------------------------------
    st.append(PageBreak())
    st.append(Paragraph("Evidence", H1))
    st.append(_p("Each item was saved at the moment it was captured and sealed with a SHA-256 hash. "
                 "Change one character in a file and its hash no longer matches the list at the end.", BODY))
    ev_dir = config.EVIDENCE_DIR / result["check_id"]
    for e in result["evidence"]:
        block = [Paragraph(f"<b>{escape(e['id'])}</b> &middot; {escape(e['agent'])} &middot; {escape(_ascii(e['label']))}", H2)]
        meta = [["Source", e.get("source_url") or "(search answer, see sources inside)"],
                ["Captured (UTC)", e["captured_at"]], ["SHA-256", e["sha256"]], ["File", e["file"]]]
        if e.get("simulated"):
            meta.append(["Note", "Simulated demo capture (made-up data)"])
        t = Table([[_p(a, CELLB), Paragraph(escape(_ascii(str(b))), MONO if a == "SHA-256" else CELL)] for a, b in meta],
                  colWidths=[28 * mm, 152 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        block.append(t)
        block.append(Spacer(1, 3))
        fpath = ev_dir / e["file"]
        if e["file"].endswith(".png") and fpath.exists():
            block.append(Image(str(fpath), width=170 * mm, height=119 * mm, kind="proportional"))
        else:
            body = fpath.read_text("utf-8", "replace") if fpath.exists() else e.get("excerpt", "")
            block.append(Table([[Preformatted(_wrap(body, 112, 45), MONO)]], colWidths=[180 * mm],
                               style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8F8F8"))])))
        st.append(KeepTogether(block[:3]))
        st.extend(block[3:])

    # --- hash list ------------------------------------------------------------------
    st.append(PageBreak())
    st.append(Paragraph("Hash list", H1))
    rows = [[_p("ID", HEADC), _p("File", HEADC), _p("SHA-256", HEADC)]]
    for e in result["evidence"]:
        rows.append([_p(e["id"]), _p(e["file"]), Paragraph(e["sha256"], MONO)])
    t = Table(rows, colWidths=[12 * mm, 62 * mm, 106 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE), ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey)]))
    st.append(t)
    st.append(Spacer(1, 6))
    st.append(Paragraph(f"Manifest SHA-256 (hash of the list above): <font face='Courier'>{result['manifest_sha256']}</font>", BODY))
    st.append(_p("To verify a file: sha256sum <file>  (Linux/Mac)  or  certutil -hashfile <file> SHA256  (Windows).", SMALL))

    doc.build(st, onFirstPage=on_page, onLaterPages=on_page)
    return out_path


def build_batch_pdf(batch: dict) -> Path:
    """Generate a clean summary report PDF for batch/multi-URL verification."""
    batch_id = batch.get("batch_id", "batch")
    out_path = config.REPORT_DIR / f"Batch_{batch_id}.pdf"
    items = batch.get("items", [])

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1] - 14 * mm, A4[0], 14 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(15 * mm, A4[1] - 9 * mm, "NexVerify  |  Batch Multi-URL Verification Report")
        canvas.setFont("Helvetica", 8.5)
        canvas.drawRightString(A4[0] - 15 * mm, A4[1] - 9 * mm, f"Batch {batch_id}")
        canvas.setFillColor(GRAY)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(15 * mm, 9 * mm, "Automated assessment based on public evidence. Cybercrime helpline: 1930.")
        canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=20 * mm, bottomMargin=16 * mm,
                            title=f"NexVerify Batch Report - {batch_id}", author="NexVerify")
    st: list = []
    st.append(Paragraph(f"Batch Multi-URL Verification Report", H1))
    total = len(items)
    safe_cnt = sum(1 for it in items if it.get("verdict", {}).get("code") in ("VERIFIED_OFFICIAL", "LOW_RISK"))
    caution_cnt = sum(1 for it in items if it.get("verdict", {}).get("code") in ("CAUTION", "SUSPICIOUS"))
    high_cnt = sum(1 for it in items if it.get("verdict", {}).get("code") == "HIGH_RISK")
    unverified_cnt = sum(1 for it in items if it.get("verdict", {}).get("code") in ("UNKNOWN", "COULDNT_VERIFY"))

    summary_text = (
        f"<b>Total Checked:</b> {total} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<font color='{GREEN.hexval()}'><b>Verified Safe:</b> {safe_cnt}</font> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<font color='{AMBER.hexval()}'><b>Suspicious:</b> {caution_cnt}</font> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<font color='{RED.hexval()}'><b>High Risk:</b> {high_cnt}</font> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<font color='{GRAY.hexval()}'><b>Unverified:</b> {unverified_cnt}</font>"
    )
    st.append(Paragraph(summary_text, BODY))
    st.append(Spacer(1, 8))

    rows = [[_p("Target / URL", HEADC), _p("Category", HEADC), _p("Score", HEADC), _p("Verdict", HEADC), _p("Confidence", HEADC), _p("Key Evidence / Notes", HEADC)]]
    for it in items:
        v = it.get("verdict") or {}
        vcode = v.get("code", "UNKNOWN")
        vcol = GREEN if vcode in ("VERIFIED_OFFICIAL", "LOW_RISK") else RED if vcode == "HIGH_RISK" else AMBER if vcode in ("CAUTION", "SUSPICIOUS") else GRAY
        score_val = str(it.get("score", "?"))
        top_reason = ""
        hits = it.get("hits") or []
        if hits:
            top_reason = hits[0].get("card_en", "") or hits[0].get("claim", "")
        elif it.get("summary"):
            top_reason = it["summary"].get("en", "")[:80]

        rows.append([
            _p(_ascii(it.get("query", ""))[:32], CELLB),
            _p(_ascii(it.get("subject", {}).get("category", "general"))[:16]),
            Paragraph(f"<font color='{vcol.hexval()}'><b>{score_val}</b></font>", CELL),
            Paragraph(f"<font color='{vcol.hexval()}'><b>{escape(_ascii(v.get('label_en', vcode)))}</b></font>", CELL),
            _p(it.get("confidence", "MED")),
            _p(_ascii(top_reason)[:60]),
        ])

    t = Table(rows, colWidths=[40 * mm, 24 * mm, 14 * mm, 38 * mm, 18 * mm, 46 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE), ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    st.append(t)
    doc.build(st, onFirstPage=on_page, onLaterPages=on_page)
    return out_path
