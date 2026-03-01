"""
Generatore di report finali in formato JSON e HTML.
Il report NON include i valori originali dei dati sensibili.
"""

import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from app.models.schemas import Batch, FileRecord, FileStatus, Finding, ReviewAction

logger = logging.getLogger(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Report Pseudonimizzazione — Batch {batch_id}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #f0f2f5; color: #1a1a2e; }}
        .container {{ max-width: 960px; margin: 2rem auto; padding: 0 1rem; }}
        header {{ background: #1a1a2e; color: white; padding: 2rem; border-radius: 8px 8px 0 0; }}
        header h1 {{ font-size: 1.5rem; margin-bottom: 0.5rem; }}
        header .meta {{ font-size: 0.85rem; opacity: 0.7; }}
        .card {{ background: white; border-radius: 0 0 8px 8px; padding: 1.5rem; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 1.5rem; }}
        .card + .card {{ border-radius: 8px; }}
        h2 {{ font-size: 1.1rem; color: #1a1a2e; border-bottom: 2px solid #e0e0e0; padding-bottom: 0.5rem; margin-bottom: 1rem; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin-bottom: 1rem; }}
        .stat-box {{ background: #f8f9fa; border-radius: 6px; padding: 1rem; text-align: center; }}
        .stat-box .value {{ font-size: 2rem; font-weight: 700; color: #2563eb; }}
        .stat-box .label {{ font-size: 0.8rem; color: #666; margin-top: 0.25rem; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
        th {{ background: #f0f2f5; text-align: left; padding: 0.6rem 0.8rem; font-weight: 600; }}
        td {{ padding: 0.6rem 0.8rem; border-bottom: 1px solid #f0f2f5; }}
        tr:last-child td {{ border-bottom: none; }}
        .badge {{ display: inline-block; padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }}
        .badge-ok {{ background: #d1fae5; color: #065f46; }}
        .badge-warn {{ background: #fef3c7; color: #92400e; }}
        .badge-err {{ background: #fee2e2; color: #991b1b; }}
        .badge-skip {{ background: #e0e7ff; color: #3730a3; }}
        .warning-box {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 0.8rem 1rem; border-radius: 0 6px 6px 0; margin-bottom: 0.5rem; font-size: 0.9rem; }}
        .risk-box {{ border-left: 4px solid #dc2626; background: #fee2e2; padding: 0.8rem 1rem; border-radius: 0 6px 6px 0; margin-bottom: 0.5rem; font-size: 0.9rem; }}
        .risk-safe {{ border-left-color: #16a34a; background: #dcfce7; }}
        .risk-warn {{ border-left-color: #d97706; background: #fef3c7; }}
        .type-bar {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem; }}
        .type-bar .bar {{ height: 18px; background: #2563eb; border-radius: 3px; min-width: 4px; }}
        .type-bar .type-name {{ font-size: 0.85rem; min-width: 160px; }}
        .type-bar .count {{ font-size: 0.85rem; color: #666; }}
        footer {{ text-align: center; font-size: 0.8rem; color: #999; padding: 1rem; }}
        .dry-run-banner {{ background: #e0e7ff; border: 2px solid #6366f1; border-radius: 8px; padding: 1rem; margin-bottom: 1.5rem; color: #3730a3; font-weight: 600; text-align: center; }}
    </style>
</head>
<body>
<div class="container">
    <header>
        <h1>Report di Pseudonimizzazione</h1>
        <div class="meta">
            Batch ID: {batch_id} &nbsp;|&nbsp;
            Modalità: {mode} &nbsp;|&nbsp;
            Completato: {completed_at}
        </div>
    </header>

    {dry_run_banner}

    <div class="card">
        <h2>Riepilogo</h2>
        <div class="stats-grid">
            <div class="stat-box"><div class="value">{total_files}</div><div class="label">File Totali</div></div>
            <div class="stat-box"><div class="value">{files_processed}</div><div class="label">Processati</div></div>
            <div class="stat-box"><div class="value">{files_failed}</div><div class="label">Falliti</div></div>
            <div class="stat-box"><div class="value">{total_findings}</div><div class="label">Entità Rilevate</div></div>
            <div class="stat-box"><div class="value">{entities_applied}</div><div class="label">Sostituzioni Applicate</div></div>
        </div>
    </div>

    <div class="card">
        <h2>Entità per Tipo</h2>
        {findings_by_type_html}
    </div>

    {residual_risk_section}

    <div class="card">
        <h2>Dettaglio File</h2>
        <table>
            <thead><tr><th>File</th><th>Stato</th><th>Entità</th><th>Note</th></tr></thead>
            <tbody>
                {files_rows}
            </tbody>
        </table>
    </div>

    {warnings_section}

    <footer>
        Generato da Local Pseudonymization Tool (MVP) — Solo uso locale, nessun dato inviato all'esterno.
    </footer>
</div>
</body>
</html>"""


def _status_badge(status: str) -> str:
    cls_map = {
        "processed": "badge-ok",
        "parsed": "badge-ok",
        "failed": "badge-err",
        "skipped": "badge-skip",
        "queued": "badge-warn",
    }
    cls = cls_map.get(status.lower(), "badge-warn")
    return f'<span class="badge {cls}">{status}</span>'


def build_report_data(
    batch: Batch,
    findings: List[Finding],
    started_at: str,
    completed_at: str,
) -> Dict[str, Any]:
    """
    Costruisce il dizionario dati del report.
    NON include i valori originali dei dati sensibili.
    """
    # Conta le entità per tipo
    findings_by_type = Counter(f.entity_type.value for f in findings)

    # Conta le sostituzioni effettivamente applicate
    entities_applied = sum(1 for f in findings if f.review_action != ReviewAction.REJECT)

    # Dettaglio file
    files_detail = []
    for file_rec in batch.files:
        file_findings = [f for f in findings if f.file_id == file_rec.file_id]
        files_detail.append(
            {
                "file_id": file_rec.file_id,
                "original_name": file_rec.original_name,
                "status": file_rec.status.value,
                "findings_count": len(file_findings),
                "warnings": file_rec.warnings,
                "error_message": file_rec.error_message,
            }
        )

    # Warning globali
    global_warnings = []
    for file_rec in batch.files:
        for w in file_rec.warnings:
            global_warnings.append(f"[{file_rec.original_name}] {w}")

    return {
        "batch_id": batch.batch_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "config": {
            "mode": batch.config.mode.value,
            "is_dry_run": batch.config.is_dry_run,
        },
        "summary": {
            "total_files": len(batch.files),
            "files_processed": sum(1 for f in batch.files if f.status in (FileStatus.PROCESSED, FileStatus.PARSED)),
            "files_failed": sum(1 for f in batch.files if f.status == FileStatus.FAILED),
            "files_with_warnings": sum(1 for f in batch.files if f.warnings),
            "total_findings": len(findings),
            "entities_applied": entities_applied,
        },
        "findings_by_type": dict(findings_by_type),
        "files_detail": files_detail,
        "global_warnings": global_warnings,
        "safety_label": batch.safety_label.value if hasattr(batch.safety_label, "value") else str(batch.safety_label),
        "residual_warnings": batch.residual_warnings,
        "security_note": (
            "Questo report non contiene i valori originali dei dati sensibili. "
            "I valori originali sono conservati esclusivamente nel file di mapping cifrato."
        ),
    }


def generate_json_report(report_data: Dict[str, Any], output_path: Path) -> None:
    """Salva il report in formato JSON."""
    output_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Report JSON generato: %s", output_path)


def generate_html_report(report_data: Dict[str, Any], output_path: Path) -> None:
    """Genera il report in formato HTML."""
    summary = report_data.get("summary", {})
    config = report_data.get("config", {})

    # Dry-run banner
    dry_run_banner = ""
    if config.get("is_dry_run"):
        dry_run_banner = '<div class="dry-run-banner">⚠ MODALITÀ DRY-RUN: Nessuna modifica è stata applicata ai file originali.</div>'

    # Barre per tipo di entità
    findings_by_type = report_data.get("findings_by_type", {})
    max_count = max(findings_by_type.values(), default=1)
    type_bars = []
    for entity_type, count in sorted(findings_by_type.items(), key=lambda x: -x[1]):
        bar_width = max(4, int(count / max_count * 300))
        type_bars.append(
            f'<div class="type-bar">'
            f'<span class="type-name">{entity_type}</span>'
            f'<div class="bar" style="width:{bar_width}px"></div>'
            f'<span class="count">{count}</span>'
            f"</div>"
        )
    findings_by_type_html = "\n".join(type_bars) if type_bars else "<p>Nessuna entità rilevata.</p>"

    # Righe tabella file
    files_rows = []
    for fd in report_data.get("files_detail", []):
        note = fd.get("error_message") or (
            "; ".join(fd.get("warnings", []))[:100] + "..." if fd.get("warnings") else "—"
        )
        files_rows.append(
            f"<tr>"
            f"<td>{fd['original_name']}</td>"
            f"<td>{_status_badge(fd['status'])}</td>"
            f"<td>{fd['findings_count']}</td>"
            f"<td style='font-size:0.8rem;color:#666'>{note}</td>"
            f"</tr>"
        )

    # Sezione warning
    global_warnings = report_data.get("global_warnings", [])
    warnings_section = ""
    if global_warnings:
        warnings_html = "\n".join(f'<div class="warning-box">{w}</div>' for w in global_warnings)
        warnings_section = f'<div class="card"><h2>Warning e Limitazioni</h2>{warnings_html}</div>'

    safety_label = report_data.get("safety_label", "SAFE_TO_UPLOAD")
    residual_warnings = report_data.get("residual_warnings", [])
    risk_cls = (
        "risk-safe"
        if safety_label == "SAFE_TO_UPLOAD"
        else ("risk-warn" if safety_label == "SAFE_WITH_WARNINGS" else "")
    )
    residual_rows = (
        "" if not residual_warnings else "<ul>" + "".join(f"<li>{w}</li>" for w in residual_warnings) + "</ul>"
    )
    residual_risk_section = (
        f'<div class="card"><h2>Residual Risk</h2>'
        f'<div class="risk-box {risk_cls}"><b>Safety Label:</b> {safety_label}</div>'
        f'{residual_rows if residual_rows else "<p>Nessun residual warning rilevato.</p>"}'
        f"</div>"
    )

    html = HTML_TEMPLATE.format(
        batch_id=report_data.get("batch_id", "N/A"),
        mode=config.get("mode", "N/A").upper(),
        completed_at=report_data.get("completed_at", "N/A"),
        dry_run_banner=dry_run_banner,
        total_files=summary.get("total_files", 0),
        files_processed=summary.get("files_processed", 0),
        files_failed=summary.get("files_failed", 0),
        total_findings=summary.get("total_findings", 0),
        entities_applied=summary.get("entities_applied", 0),
        findings_by_type_html=findings_by_type_html,
        residual_risk_section=residual_risk_section,
        files_rows="\n".join(files_rows),
        warnings_section=warnings_section,
    )

    output_path.write_text(html, encoding="utf-8")
    logger.info("Report HTML generato: %s", output_path)
