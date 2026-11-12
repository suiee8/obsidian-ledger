"""Export a Coach report as Markdown, or as a print-friendly HTML page.

Both are built from the same report object, so the numbers match the app. HTML output escapes
every value, has no scripts, and uses only plain black-on-white styling so it prints cleanly.
"""

from __future__ import annotations

import csv
import html
import io

from obsidian_ledger.coach.models import CoachReport, Finding
from obsidian_ledger.csvsafe import neutralize_cell

DISCLAIMER = (
    "Past performance review only. Obsidian Ledger does not give financial advice or trade signals."
)


def _finding_lines(finding: Finding) -> list[str]:
    lines = [
        f"### {finding.title}",
        f"- Confidence: {finding.confidence}",
        f"- Trades: {finding.n.display}",
        f"- Average per trade: {finding.mean_currency.display} "
        f"({finding.effect_currency.display} against your other trades)",
    ]
    if finding.interval_currency is not None:
        interval = finding.interval_currency
        lines.append(
            f"- 95% interval for that gap: {interval.low.display} to {interval.high.display}"
        )
    lines.append(f"- What if: {finding.what_if.description}")
    lines.append(f"- Rule: {finding.rule}")
    if finding.evidence:
        ids = ", ".join(item.trade_id for item in finding.evidence)
        lines.append(f"- Evidence trades: {ids}")
    return lines


def to_markdown(report: CoachReport) -> str:
    out: list[str] = [
        "# Coach report",
        f"Generated {report.generated_at} from {report.sample_trades.display} trades. "
        f"Data version {report.dataset_version}.",
        "",
        f"## Verdict: {report.verdict.headline} ({report.verdict.confidence} confidence)",
        *[f"- {line}" for line in report.verdict.lines],
        f"- Basis: {report.verdict.basis}.",
        "",
    ]
    sections = (
        ("Top leaks", report.top_leaks),
        ("Top strengths", report.top_strengths),
        ("Behavior patterns", report.behavior_patterns),
        ("Low-confidence leads", report.low_confidence_leads),
    )
    for heading, findings in sections:
        out.append(f"## {heading}")
        if not findings:
            out += ["None cleared the filters.", ""]
            continue
        for finding in findings:
            out += _finding_lines(finding) + [""]
    out.append("## Risk review")
    out += [f"- {item.title}: {item.figure.display}. {item.note}" for item in report.risk_review]
    out += ["", "## 7-day action plan"]
    out += [f"{item.day}. **{item.focus}**: {item.task}" for item in report.action_plan]
    out += ["", "## Pre-trade checklist"]
    out += [f"- [ ] {item.question} {item.reason}" for item in report.checklist]
    if report.change_vs_previous is not None:
        out += ["", "## Change since the previous report"]
        out += [
            f"- {item.label}: {item.previous.display} to {item.current.display}"
            for item in report.change_vs_previous.metrics
        ]
    out += ["", "## Data caveats"]
    out += [f"- {caveat.text}" for caveat in report.caveats]
    out += ["", f"_{DISCLAIMER}_", ""]
    return "\n".join(out)


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def to_html(report: CoachReport) -> str:
    def paragraph(text: str) -> str:
        return f"<p>{_escape(text)}</p>"

    def listing(items: list[str]) -> str:
        return "<ul>" + "".join(f"<li>{_escape(item)}</li>" for item in items) + "</ul>"

    parts: list[str] = [
        "<h1>Coach report</h1>",
        paragraph(f"Generated {report.generated_at} from {report.sample_trades.display} trades."),
        f"<h2>Verdict: {_escape(report.verdict.headline)} "
        f"({_escape(report.verdict.confidence)} confidence)</h2>",
        listing(report.verdict.lines),
    ]
    sections = (
        ("Top leaks", report.top_leaks),
        ("Top strengths", report.top_strengths),
        ("Behavior patterns", report.behavior_patterns),
    )
    for heading, findings in sections:
        parts.append(f"<h2>{_escape(heading)}</h2>")
        if not findings:
            parts.append(paragraph("None cleared the filters."))
        for finding in findings:
            parts.append(f"<h3>{_escape(finding.title)}</h3>")
            parts.append(
                listing(
                    [
                        f"Confidence: {finding.confidence}",
                        f"Trades: {finding.n.display}",
                        f"Average per trade: {finding.mean_currency.display}",
                        f"What if: {finding.what_if.description}",
                        f"Rule: {finding.rule}",
                    ]
                )
            )
    parts.append("<h2>Risk review</h2>")
    parts.append(listing([f"{i.title}: {i.figure.display}" for i in report.risk_review]))
    parts.append("<h2>7-day action plan</h2>")
    parts.append(listing([f"Day {i.day}, {i.focus}: {i.task}" for i in report.action_plan]))
    parts.append("<h2>Pre-trade checklist</h2>")
    parts.append(listing([f"{i.question} {i.reason}" for i in report.checklist]))
    parts.append("<h2>Data caveats</h2>")
    parts.append(listing([c.text for c in report.caveats]))
    parts.append(f"<p><em>{_escape(DISCLAIMER)}</em></p>")
    style = (
        "body{font:14px/1.5 Georgia,serif;max-width:46rem;margin:2rem auto;"
        "color:black;background:white}"
        "h1,h2,h3{font-family:Arial,sans-serif}"
        "h2{border-bottom:1px solid gray;padding-bottom:.2rem}"
        "@media print{body{margin:0}h2{break-after:avoid}li{break-inside:avoid}}"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<title>Coach report</title>"
        f"<style>{style}</style></head><body>{''.join(parts)}</body></html>"
    )


def to_csv(report: CoachReport) -> str:
    """Export the Coach report findings and metrics as CSV with neutralized cells."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([
        neutralize_cell("section"),
        neutralize_cell("title"),
        neutralize_cell("confidence"),
        neutralize_cell("trades_count"),
        neutralize_cell("mean_value"),
        neutralize_cell("effect_value"),
        neutralize_cell("rule"),
        neutralize_cell("description"),
    ])
    sections = (
        ("Top leaks", report.top_leaks),
        ("Top strengths", report.top_strengths),
        ("Behavior patterns", report.behavior_patterns),
        ("Low-confidence leads", report.low_confidence_leads),
    )
    for section_name, findings in sections:
        for f in findings:
            writer.writerow([
                neutralize_cell(section_name),
                neutralize_cell(f.title),
                neutralize_cell(f.confidence),
                str(f.n.value),
                str(f.mean_currency.value),
                str(f.effect_currency.value),
                neutralize_cell(f.rule),
                neutralize_cell(f.what_if.description),
            ])
    return buffer.getvalue()

