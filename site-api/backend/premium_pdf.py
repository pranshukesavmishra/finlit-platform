"""Render the current on-demand report; never fetch or recalculate at download time."""
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.graphics.shapes import Drawing, String, Line, Circle

try:
    from .premium_presentation import build_report_review
except ImportError:
    from premium_presentation import build_report_review

NAVY = colors.HexColor("#10233D")
GOLD = colors.HexColor("#B5822E")
MUTED = colors.HexColor("#57677A")
PALE = colors.HexColor("#F0F4F8")


def text(value):
    return escape(str(value if value is not None else "Not available")).replace("\n", "<br/>")


def number(value, suffix=""):
    return f"{value:,.2f}{suffix}" if isinstance(value, (int, float)) else "N/A"


def render_premium_pdf(report):
    output = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", fontName="Helvetica-Bold", fontSize=27, leading=32, textColor=NAVY, spaceAfter=14))
    styles.add(ParagraphStyle(name="SectionTitle", fontName="Helvetica-Bold", fontSize=16, leading=21, textColor=NAVY, spaceBefore=14, spaceAfter=9))
    styles.add(ParagraphStyle(name="BodyCopy", fontName="Helvetica", fontSize=9, leading=14, textColor=MUTED, spaceAfter=7))
    styles.add(ParagraphStyle(name="CellCopy", fontName="Helvetica", fontSize=8, leading=11, textColor=NAVY))
    styles.add(ParagraphStyle(name="CellSmall", fontName="Helvetica", fontSize=7, leading=9, textColor=NAVY))
    styles.add(ParagraphStyle(name="GoldLabel", fontName="Helvetica-Bold", fontSize=9, leading=13, textColor=GOLD, spaceAfter=10))
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=19*mm, leftMargin=19*mm, topMargin=23*mm, bottomMargin=22*mm,
                            title=f"FinLit Premium Report - {report['company']['symbol']}", author="FinLit Ventures")
    story = []
    p = lambda value, style="BodyCopy": Paragraph(text(value), styles[style])
    def section(title): story.append(p(title, "SectionTitle"))
    def table(rows, widths, compact=False, style=None):
        cells = [[p(cell, style or ("CellSmall" if compact else "CellCopy")) for cell in row] for row in rows]
        t = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), PALE), ("VALIGN", (0,0), (-1,-1), "TOP"),
                               ("LEFTPADDING", (0,0), (-1,-1), 4 if compact else 8), ("RIGHTPADDING", (0,0), (-1,-1), 4 if compact else 8),
                               ("TOPPADDING", (0,0), (-1,-1), 5 if compact else 8), ("BOTTOMPADDING", (0,0), (-1,-1), 5 if compact else 8),
                               ("LINEBELOW", (0,0), (-1,0), .8, GOLD), ("LINEBELOW", (0,1), (-1,-1), .3, colors.HexColor("#DDE3EB"))]))
        story.append(t)
    company, rating = report["company"], report["rating"]
    review = build_report_review(report)
    rated = rating["status"] != "NOT RATED"
    story.append(p("FINLIT VENTURES / EQUITY RESEARCH", "GoldLabel"))
    story.append(p("Premium Company Report", "ReportTitle"))
    story.append(p(company["name"], "SectionTitle"))
    story.append(p(f"{company['symbol']} | {company.get('industry') or 'Industry unavailable'} | {report['statementType'].title()} statements"))
    generated = datetime.fromisoformat(report["createdAt"]).astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p IST")
    story.append(p(f"Generated {generated}"))
    story.append(Spacer(1, 7*mm))
    score = number(rating["final"]) + " / 100" if rated else "NOT RATED"
    story.append(p(score, "ReportTitle"))
    story.append(p(f"{rating['label']} | {rating['status']} | Input coverage {rating['confidence'] * 100:.0f}%", "GoldLabel"))
    story.append(p("Financial health assessment across business performance, valuation, financial quality and market risk."))
    story.append(p("Data coverage shows how much of the required information is available."))
    section("Assessment at a glance")
    rows = [["Category", "Score / 100", "Data coverage"]]
    for part in ("fundamental", "valuation", "quality", "risk"):
        rows.append([part.title(), number(rating["parts"][part]) if rated else "Not rated", f"{rating['coverage'][part]*100:.0f}%"])
    table(rows, [210, 130, 147])
    section("Data dates")
    meta = report["inputMeta"]
    story.append(p(" | ".join(f"{label}: {meta.get(key) or 'unavailable'}" for key,label in (("quarterlyAsOf","Quarter"),("annualAsOf","Financial year"),("balanceAsOf","Balance sheet"),("ownershipAsOf","Ownership"),("priceAsOf","Price")))))
    story.append(p("This is a current model-based financial health assessment, not a target price or an investment recommendation. Market, accounting and data-provider limitations apply."))
    story.append(PageBreak())
    story.append(p("Business performance", "ReportTitle"))
    section("Annual business performance")
    rows = [["Financial year", "Revenue / NII (Cr)", "Net profit (Cr)", "EPS (INR)"]]
    for row in report.get("trends", []): rows.append([row["period"], number(row["revenue"]), number(row["profit"]), number(row["eps"])])
    table(rows, [100, 140, 130, 117])
    # Three small, independently scaled trends keep EPS separate from monetary amounts.
    trends = report.get("trends", [])
    if len(trends) >= 2:
        drawing = Drawing(487, 112)
        for chart_index, (key, title, unit, colour) in enumerate((("revenue", "Revenue / NII", "Cr", GOLD), ("profit", "Net profit", "Cr", colors.HexColor("#31846C")), ("eps", "EPS", "INR/share", colors.HexColor("#476DAB")))):
            offset = chart_index * 166
            drawing.add(String(offset + 4, 96, title, fontName="Helvetica-Bold", fontSize=9, fillColor=NAVY))
            values = [row.get(key) for row in trends if row.get(key) is not None]
            if not values:
                drawing.add(String(offset + 4, 55, "No comparable data", fontSize=8, fillColor=MUTED))
                continue
            low, high = min(values), max(values)
            span = high - low or 1
            previous = None
            for index, row in enumerate(trends):
                value = row.get(key)
                if value is None:
                    previous = None
                    continue
                x, y = offset + 7 + index / (len(trends) - 1) * 140, 35 + (value - low) / span * 40
                if previous: drawing.add(Line(previous[0], previous[1], x, y, strokeColor=colour, strokeWidth=1.8))
                drawing.add(Circle(x, y, 2, fillColor=colour, strokeColor=colour))
                previous = (x, y)
            drawing.add(String(offset + 4, 15, f"{trends[0]['period']} - {trends[-1]['period']} | {unit}", fontSize=7, fillColor=MUTED))
        story.append(Spacer(1, 5*mm))
        story.append(drawing)
    story.append(PageBreak())
    story.append(p("Review notes", "ReportTitle"))
    completeness = review['completeness']
    section("Input completeness")
    if completeness['complete']:
        story.append(p("All applicable scoring factors have usable inputs and the required comparison history."))
    else:
        story.append(p(f"Unavailable factors: {completeness['missingFactorCount']}. Factors with limited comparison history: {completeness['limitedHistoryCount']}. These limitations remain visible even where an input is excluded from the coverage percentage."))
        for item in completeness['items']:
            story.append(p(f"{item['category']} / {item['label']}: {item['reason']} {item['treatment']}"))
    section("What to keep in mind")
    for note in review["notes"]:
        story.append(p("- " + note))
    if not review["notes"]:
        story.append(p("No material data limitations identified for this assessment."))
    story.append(p("Pros and cons reflect the company's assessment for its industry. Mixed results are shown separately. Unavailable information is not treated as a company strength or weakness."))
    story.append(p("Higher Risk scores indicate lower assessed risk. This assessment is based on available information and does not predict future returns."))
    for index, part in enumerate(review["parts"]):
        if index in (0, 2):
            story.append(PageBreak())
            story.append(p("Business & valuation" if index == 0 else "Quality & risk", "ReportTitle"))
        section(part["name"] + " | " + (number(part["score"]) + " / 100" if part["score"] is not None else "Not rated"))
        for note in part.get("notes", []):
            story.append(p(note, "BodyCopy"))
        def entries(items, empty):
            if not items: return empty
            return "\n\n".join(f"{item['label']}: {item['valueText']}. {item['summary']}" + (" " + item['comparisonText'] if item.get('comparisonText') else "") for item in items)
        table([["Pros", "Cons"], [entries(part["pros"], "No clear strengths identified."), entries(part["cons"], "No major concerns identified.")]], [243.5, 243.5], compact=True, style="BodyCopy")
        for key, label in (("mixed", "Mixed factors"), ("unavailable", "Unavailable information")):
            if part[key]:
                story.append(p(label, "GoldLabel"))
                for item in part[key]:
                    story.append(p(f"{item['label']}: {item['valueText']}. {item['summary']}" + (" " + item['comparisonText'] if item.get('comparisonText') else ""), "BodyCopy"))
    trace = report.get("calculationTrace")
    if trace:
        story.append(PageBreak())
        story.append(p("Financial history", "ReportTitle"))
        story.append(p(f"{report['statementType'].title()} financial statements. Amounts in INR crore; EPS in INR per share."))
        story.append(p("Periods run oldest to newest. N/A indicates unavailable information."))
        sales_label = "Net interest income" if rating['group'] in ("BANK","NBFC") else "Net premium income" if rating['group']=="INSURANCE" else "Sales"
        section("Quarterly results")
        for offset in range(0,len(trace['quarterly']),7):
            chunk=trace['quarterly'][offset:offset+7]
            rows=[["Measure"]+[r['period'] for r in chunk]]
            for key,label in (("sales",sales_label),("profit","Owner-attributable profit"),("ebitda","EBITDA"),("eps","EPS (INR)")):
                rows.append([label]+[number(r.get(key)) for r in chunk])
            table(rows,[120]+[367/len(chunk)]*len(chunk),compact=True)
            story.append(Spacer(1,4*mm))
        if not trace['quarterly']: story.append(p("Quarterly results unavailable for this statement basis."))
        section("Annual results")
        if trace['annual']:
            rows=[["Measure"]+[r['period'] for r in trace['annual']]]
            for key,label in (("sales",sales_label),("profit","Owner-attributable profit"),("cashFlow","Operating cash flow"),("netWorth","Book equity")):
                rows.append([label]+[number(r.get(key)) for r in trace['annual']])
            table(rows,[120]+[367/len(trace['annual'])]*len(trace['annual']),compact=True)
        else: story.append(p("Annual results unavailable for this statement basis."))
        story.append(PageBreak())
        story.append(p("Key financial ratios", "ReportTitle"))
        story.append(p("Current financial and market information used in this assessment. N/A indicates unavailable information."))
        latest=trace['latest']
        rows=[["Measure", "Value", "Measure", "Value"]]
        for index in range(0,len(latest),2):
            pair=[]
            for r in latest[index:index+2]: pair.extend([('Shares outstanding' if r['key'] == 'shares' else r['label']),number(r['value']," "+r['unit'])])
            rows.append(pair+[""]*(4-len(pair)))
        table(rows,[135,108,135,109],compact=True)
    def footer(canvas, doc):
        canvas.saveState()
        w,h = A4
        canvas.setStrokeColor(GOLD); canvas.line(19*mm, h-16*mm, w-19*mm, h-16*mm)
        canvas.setFont("Helvetica-Bold",8); canvas.setFillColor(NAVY); canvas.drawString(19*mm,h-13*mm,"FINLIT / PREMIUM RESEARCH")
        canvas.setFont("Helvetica",7); canvas.setFillColor(MUTED)
        canvas.drawString(19*mm,13*mm,f"{company['symbol']} | FinLit Ventures")
        canvas.drawRightString(w-19*mm,13*mm,f"Page {doc.page}")
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
