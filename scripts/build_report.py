"""
Generate the project report PDF (docs/Airline_Data_Platform_Report.pdf).

A self-contained study + showcase document: what was built, the architecture,
the design decisions, what the project teaches, and an interview-prep Q&A.

    python scripts/build_report.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, Image, ListFlowable, ListItem, PageBreak, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "img"
OUT = ROOT / "docs" / "Airline_Data_Platform_Report.pdf"

NAVY = colors.HexColor("#1f3b5c")
TEAL = colors.HexColor("#2a9d8f")
AMBER = colors.HexColor("#b45309")
LIGHT = colors.HexColor("#eef2f7")
GREY = colors.HexColor("#475569")

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=NAVY, fontSize=17,
                    spaceBefore=14, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=TEAL, fontSize=13,
                    spaceBefore=10, spaceAfter=5)
BODY = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10.5, leading=15,
                      alignment=TA_JUSTIFY, spaceAfter=6)
BULLET = ParagraphStyle("Bullet", parent=BODY, alignment=TA_LEFT, spaceAfter=3)
SMALL = ParagraphStyle("Small", parent=styles["Normal"], fontSize=9, textColor=GREY)
QSTYLE = ParagraphStyle("Q", parent=BODY, alignment=TA_LEFT, textColor=NAVY,
                        fontName="Helvetica-Bold", spaceBefore=8, spaceAfter=2)


def img(path: Path, width_in: float):
    from PIL import Image as PILImage
    w, h = PILImage.open(path).size
    width = width_in * inch
    return Image(str(path), width=width, height=width * h / w)


def bullets(items):
    return ListFlowable(
        [ListItem(Paragraph(t, BULLET), leftIndent=8, value="•") for t in items],
        bulletType="bullet", start="•", leftIndent=12,
    )


def kv_table(rows, col_widths):
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def qa(story, q, a):
    story.append(Paragraph("Q. " + q, QSTYLE))
    story.append(Paragraph("A. " + a, BODY))


def build():
    doc = SimpleDocTemplate(str(OUT), pagesize=LETTER,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                            leftMargin=0.85 * inch, rightMargin=0.85 * inch,
                            title="Airline Data Platform - Project Report",
                            author="Dhanush Battina")
    s = []

    # ---------------- cover ----------------
    s.append(Spacer(1, 1.3 * inch))
    s.append(Paragraph("AI-Ready Airline Data Pipeline<br/>&amp; Analytics Platform",
                       ParagraphStyle("T", parent=styles["Title"], textColor=NAVY,
                                      fontSize=26, leading=32, alignment=TA_CENTER)))
    s.append(Spacer(1, 12))
    s.append(Paragraph("Data Engineering Portfolio — Project Report",
                       ParagraphStyle("ST", parent=styles["Normal"], fontSize=13,
                                      textColor=TEAL, alignment=TA_CENTER)))
    s.append(Spacer(1, 24))
    s.append(HRFlowable(width="60%", thickness=1.2, color=colors.HexColor("#cbd5e1")))
    s.append(Spacer(1, 18))
    s.append(Paragraph(
        "End-to-end platform that ingests airline operational data, validates and "
        "models it into a tested star schema, and serves analytics — running "
        "locally on DuckDB and shipping to Snowflake unchanged.",
        ParagraphStyle("cap", parent=BODY, alignment=TA_CENTER, textColor=GREY)))
    s.append(Spacer(1, 30))
    s.append(img(IMG / "architecture.png", 6.4))
    s.append(Spacer(1, 20))
    s.append(Paragraph("Python · SQL · dbt · Apache Airflow · Great Expectations · "
                       "DuckDB / Snowflake · Power BI · Docker",
                       ParagraphStyle("stack", parent=SMALL, alignment=TA_CENTER)))
    s.append(Paragraph("Author: Dhanush Battina",
                       ParagraphStyle("auth", parent=SMALL, alignment=TA_CENTER)))
    s.append(PageBreak())

    # ---------------- 1. Executive summary ----------------
    s.append(Paragraph("1. Executive summary", H1))
    s.append(Paragraph(
        "This project is a production-shaped data platform for airline operations. "
        "It ingests four sources — flights, airports, carriers and weather — cleans "
        "and validates them, models them into a Kimball star schema with dbt, and "
        "exposes the results through a Power BI semantic model and a runnable "
        "Streamlit dashboard. The entire pipeline is orchestrated by Apache Airflow "
        "and packaged with Docker. Its defining property is <b>local-first, "
        "cloud-ready</b>: it runs end-to-end on a laptop against an embedded DuckDB "
        "warehouse, yet the identical dbt models target Snowflake by switching a "
        "single profile.", BODY))
    s.append(Paragraph(
        "The goal was not just to move data, but to do it the way a real data team "
        "does: layered modelling, enforced data quality, referential-integrity "
        "testing, row-count reconciliation, orchestration, and BI — each an "
        "explicit, inspectable part of the repository.", BODY))

    # ---------------- 2. What I built ----------------
    s.append(Paragraph("2. What I built", H1))
    s.append(bullets([
        "<b>Ingestion (ETL):</b> a Talend-style extract + load that lands four raw "
        "sources into the warehouse with audit columns and an ingestion-audit log.",
        "<b>Dimensional model (dbt):</b> a star schema — <i>fact_flights</i> and "
        "<i>fact_flight_delays</i> around conformed <i>dim_date</i>, "
        "<i>dim_airport</i> and <i>dim_airline</i> — with surrogate keys.",
        "<b>Data quality:</b> Great Expectations on the raw layer, 30 dbt tests on "
        "the modelled layers, and a source-to-target row-count reconciliation.",
        "<b>Orchestration:</b> an Airflow DAG for the daily batch plus a no-Docker "
        "Python runner for instant local demos.",
        "<b>Analytics:</b> four business marts (route performance, delay trends, "
        "cancellations, operational KPIs) surfaced in Power BI and Streamlit.",
    ]))

    # ---------------- 3. Architecture ----------------
    s.append(Paragraph("3. Architecture &amp; data flow", H1))
    s.append(Paragraph(
        "Data moves through clearly separated layers, each with a single "
        "responsibility. Great Expectations guards the raw layer; dbt tests guard "
        "every modelled layer; reconciliation proves nothing is silently lost.", BODY))
    s.append(bullets([
        "<b>Sources → Ingestion:</b> extract profiles each file; load full-refreshes "
        "the raw schema idempotently and records rows-extracted vs rows-loaded.",
        "<b>Raw → Staging:</b> dbt views de-duplicate, null-out sentinel values, "
        "drop orphan-airport flights, standardize codes, and derive delay flags.",
        "<b>Staging → Dimensions/Facts → Marts:</b> the star schema is built and "
        "aggregated into analytics tables.",
        "<b>Marts → BI:</b> Power BI and Streamlit read the same marts, so both "
        "always agree.",
    ]))

    # ---------------- 4. Data model ----------------
    s.append(Paragraph("4. The data model", H1))
    s.append(Paragraph(
        "A classic star schema at the grain of <b>one row per flight</b>. Facts hold "
        "measures and foreign keys; dimensions hold descriptive attributes. "
        "Surrogate keys are hashed so joins never depend on messy natural codes.", BODY))
    s.append(Spacer(1, 4))
    s.append(kv_table([
        ["Table", "Type", "Grain / purpose"],
        ["fact_flights", "Fact", "one row per flight; delay measures + FKs"],
        ["fact_flight_delays", "Fact", "one row per flight × delay cause (unpivoted)"],
        ["dim_date", "Dimension", "calendar attributes (conformed)"],
        ["dim_airport", "Dimension", "airport + hub flag + region"],
        ["dim_airline", "Dimension", "carrier + carrier type"],
        ["route_performance / delay_trends", "Mart", "aggregated analytics"],
        ["cancellations / operational_kpis", "Mart", "aggregated analytics"],
    ], [1.9 * inch, 1.0 * inch, 3.3 * inch]))

    # ---------------- 5. Data quality ----------------
    s.append(Paragraph("5. Data quality strategy", H1))
    s.append(Paragraph(
        "Quality is enforced in three complementary layers rather than assumed:", BODY))
    s.append(bullets([
        "<b>Great Expectations (raw):</b> nulls, uniqueness, schema/length, accepted "
        "values and ranges. Runs in monitor mode (reports defects) with a strict "
        "flag for a hard production gate.",
        "<b>dbt tests (modelled):</b> unique / not_null on keys, "
        "<i>relationships</i> tests that enforce fact→dimension integrity, "
        "accepted_values on categoricals, and custom singular tests.",
        "<b>Reconciliation:</b> accounts for every source row across "
        "source→raw→staging, classifying each delta as a removed duplicate or a "
        "DQ-filtered row; unexplained loss fails the build.",
    ]))
    s.append(Paragraph(
        "The synthetic data deliberately contains duplicates, -9999 sentinel delays, "
        "missing tail numbers and orphan airport codes, so these checks demonstrably "
        "catch and clean real defects.", BODY))

    # ---------------- 6. Design decisions ----------------
    s.append(Paragraph("6. Design decisions &amp; trade-offs", H1))
    s.append(kv_table([
        ["Decision", "Why"],
        ["DuckDB default, Snowflake-ready", "Zero-setup local runs; dbt makes the cloud swap a one-line profile change."],
        ["All logic in dbt", "Warehouse-portable models; no warehouse-specific scripts to rewrite."],
        ["Full-refresh loads", "Deterministic and simple at this volume; incremental is the noted next step."],
        ["GE in monitor mode", "Shows cleaning of known-dirty raw data; --strict gives a production gate."],
        ["Synthetic seeded data", "Self-contained + reproducible while exercising every DQ rule."],
    ], [2.1 * inch, 4.1 * inch]))

    # ---------------- 7. Results ----------------
    s.append(Paragraph("7. Results", H1))
    s.append(Paragraph(
        "From the default seeded run (~60k flights over one quarter): ~98% completion "
        "factor, ~77% on-time arrivals, ~7.5 min average arrival delay, with National "
        "Airspace and carrier issues the largest delay contributors and weather the "
        "dominant cancellation reason.", BODY))
    s.append(Spacer(1, 6))
    s.append(img(IMG / "dashboard_overview.png", 6.2))

    # ---------------- 8. What I learned ----------------
    s.append(Paragraph("8. What this project teaches (skills to speak to)", H1))
    s.append(bullets([
        "Designing a layered warehouse (raw → staging → marts) and why the split matters.",
        "Kimball dimensional modelling: facts, dimensions, grain, surrogate keys, conformed dimensions.",
        "Writing maintainable dbt: refs, sources, seeds, tests, macros with adapter dispatch.",
        "Operationalizing data quality with Great Expectations and reconciliation.",
        "Orchestrating a batch with Airflow and reasoning about task dependencies + retries.",
        "Making a project portable across warehouses and reproducible for anyone to run.",
    ]))

    # ---------------- 9. Interview Q&A ----------------
    s.append(PageBreak())
    s.append(Paragraph("9. Interview talking points (Q &amp; A)", H1))
    s.append(Paragraph("Be ready to answer these confidently — they map directly to the repo.", SMALL))
    qa(s, "Walk me through the architecture.",
       "Four sources are extracted and loaded into a raw schema with audit logging. "
       "Great Expectations validates the raw layer. dbt then transforms raw into "
       "staging (cleaning), a star schema (dims + facts), and analytics marts. A "
       "reconciliation step proves no rows are lost, and Airflow orchestrates the "
       "daily run. Power BI and Streamlit read the marts.")
    qa(s, "What is the grain of your fact table?",
       "One row per flight in fact_flights. fact_flight_delays is finer — one row "
       "per flight per contributing delay cause — because I unpivoted the five BTS "
       "delay-cause columns to make cause analysis a simple group-by.")
    qa(s, "Why surrogate keys instead of the natural airport/carrier codes?",
       "Surrogate keys (hashed) decouple the model from messy or changing natural "
       "keys, keep joins fast and uniform, and make it easy to introduce "
       "slowly-changing dimensions later without breaking fact joins.")
    qa(s, "How do you guarantee data quality?",
       "Three layers: Great Expectations on raw (nulls, uniqueness, schema, ranges), "
       "dbt tests on every model (including relationships tests that enforce "
       "referential integrity), and a source-to-target reconciliation that accounts "
       "for every row. Known-dirty inputs prove the checks actually fire.")
    qa(s, "What is source-to-target reconciliation and why does it matter?",
       "It compares row counts along source→raw→staging and explains every "
       "difference as either a removed duplicate or a DQ-filtered row. It catches "
       "silent data loss — the kind of bug that quietly corrupts a dashboard.")
    qa(s, "How is this portable to Snowflake?",
       "All transformation logic is in dbt, which abstracts the warehouse. Switching "
       "from DuckDB to Snowflake is a profile change plus credentials — the models, "
       "tests and business logic are identical. A dispatched macro handles the one "
       "dialect difference (title-casing).")
    qa(s, "How would you make this incremental / handle years of data?",
       "Make fact_flights an incremental model keyed on flight_date so only new "
       "partitions are processed, add dbt snapshots for slowly-changing dimensions, "
       "and stage raw files in S3 loaded to Snowflake. The full-refresh default was "
       "a deliberate simplicity choice for the demo.")
    qa(s, "Why Airflow, and how are the tasks wired?",
       "Airflow gives scheduling, retries and observability. The DAG runs "
       "generate → ingest → validate → dbt build → reconcile as a linear dependency "
       "chain; a failure in reconcile raises and fails the run so bad data never "
       "reaches BI.")
    qa(s, "What would you improve next?",
       "Incremental facts + SCD snapshots, a real BTS feed, a dbt docs/lineage site "
       "with freshness SLAs and alerting, and CI that runs dbt build + Great "
       "Expectations on every pull request.")

    # ---------------- 10. Run + present ----------------
    s.append(Paragraph("10. How to run it", H1))
    s.append(Paragraph(
        "<b>make setup</b> → install · <b>make pipeline</b> → generate, ingest, "
        "validate, dbt build, reconcile · <b>make dashboard</b> → Streamlit · "
        "<b>make docker-up</b> → Airflow + dashboard. For Snowflake: set "
        "WAREHOUSE=snowflake and the SNOWFLAKE_* variables, then "
        "<b>dbt build --target snowflake</b>.", BODY))

    s.append(Paragraph("11. Putting it on your resume &amp; LinkedIn", H1))
    s.append(Paragraph("<b>Resume bullet:</b> Built an end-to-end airline analytics "
                       "platform (Python, SQL, dbt, Airflow, Great Expectations, "
                       "DuckDB/Snowflake, Power BI, Docker) with a tested star schema, "
                       "three-layer data quality, and source-to-target reconciliation; "
                       "local-first and cloud-portable.", BODY))
    s.append(Paragraph("<b>LinkedIn line:</b> Designed and shipped a production-shaped "
                       "airline data pipeline — layered dbt modelling, enforced data "
                       "quality, Airflow orchestration, and Power BI/Streamlit "
                       "analytics — runnable on a laptop and portable to Snowflake.", BODY))

    doc.build(s)
    print(f"wrote {OUT}  ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
