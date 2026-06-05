"""Generate docs/architecture.pdf from the write-up."""

from pathlib import Path

from fpdf import FPDF

DOCS = Path(__file__).resolve().parent


def build_pdf() -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Fleet Health & Delivery Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "Architecture Write-Up - ThinkPalm AgentAI Team Alpha", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    img = DOCS / "architecture.png"
    if img.exists():
        pdf.image(str(img), w=170)
        pdf.ln(6)

    sections = [
        (
            "Problem",
            "Ship management teams receive daily data from noon reports, port schedules, "
            "bunker logs, and maintenance alerts. Manual synthesis is slow and error-prone.",
        ),
        (
            "Solution",
            "A sequential 4-agent LangGraph pipeline with Claude API tool-calling produces "
            "structured Fleet Health & Delivery Reports via FastAPI.",
        ),
        (
            "Agents",
            "1. Ingestion - parse and normalise data\n"
            "2. Anomaly - detect fuel, schedule, maintenance issues\n"
            "3. Performance - draft vessel summaries for superintendent\n"
            "4. Escalation - flag critical shore-side defects",
        ),
        (
            "Memory",
            "SQLite stores vessel snapshots, report history, agent memory, and "
            "LangGraph checkpoints.",
        ),
        (
            "Stack",
            "FastAPI, LangGraph, Claude API (Anthropic), SQLite, Pydantic, pytest",
        ),
    ]

    for title, body in sections:
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, body)
        pdf.ln(3)

    pdf.output(str(DOCS / "architecture.pdf"))
    print(f"Wrote {DOCS / 'architecture.pdf'}")


if __name__ == "__main__":
    build_pdf()
