"""E-mail alerts for failed Airflow tasks.

Configured with environment variables (pipelines/.env). If SMTP_HOST or
ALERT_EMAIL_TO is unset, alerts are only logged, so a missing mail setup never
breaks a pipeline.

    SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_STARTTLS (true)
    ALERT_EMAIL_TO, ALERT_EMAIL_FROM (defaults to SMTP_USER)
    AIRFLOW_UI_URL (http://127.0.0.1:8080) — used for links in the e-mail
"""

import json
import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger(__name__)

DBT_TARGET = Path(os.getenv("DBT_PROJECT_DIR", "/opt/airflow/project/warehouse")) / "target"


def send_email(subject: str, body: str) -> bool:
    host, to = os.getenv("SMTP_HOST"), os.getenv("ALERT_EMAIL_TO")
    if not host or not to:
        logger.warning(f"Alert not e-mailed (SMTP_HOST/ALERT_EMAIL_TO unset): {subject}\n{body}")
        return False

    user = os.getenv("SMTP_USER")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("ALERT_EMAIL_FROM") or user or "dublinbikes@localhost"
    msg["To"] = to
    msg.set_content(body)

    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", 587)), timeout=20) as smtp:
        if os.getenv("SMTP_STARTTLS", "true").lower() == "true":
            smtp.starttls()
        if user:
            smtp.login(user, os.getenv("SMTP_PASSWORD", ""))
        smtp.send_message(msg)
    logger.info(f"Alert e-mailed to {to}: {subject}")
    return True


def dbt_failures(target: Path | None = None, artifact: str = "run_results.json") -> list[str]:
    """Failed nodes from a dbt artifact (run_results.json for build, sources.json
    for source freshness), one line each."""
    target = target or DBT_TARGET
    try:
        results = json.loads((target / artifact).read_text())["results"]
    except (OSError, ValueError, KeyError):
        return []
    if artifact == "sources.json":
        return [
            f"- {r['unique_id']}: {r['status']} — last loaded "
            f"{r.get('max_loaded_at_time_ago_in_s', 0) / 3600:.1f} h ago"
            for r in results if r.get("status") in ("error", "runtime error")
        ]
    return [
        f"- {r['unique_id']}: {r['status']}" + (f" ({r['failures']} rows)" if r.get("failures") else "")
        + (f"\n    {(r.get('message') or '').strip()[:300]}" if r.get("message") else "")
        for r in results
        if r.get("status") in ("fail", "error", "runtime error")
    ]


def build_failure_message(context: dict) -> tuple[str, str]:
    ti = context["ti"]
    dag_id, task_id, run_id = ti.dag_id, ti.task_id, ti.run_id
    ui = os.getenv("AIRFLOW_UI_URL", "http://127.0.0.1:8080").rstrip("/")
    lines = [
        f"DAG:     {dag_id}",
        f"Task:    {task_id}",
        f"Run:     {run_id}",
        f"Attempt: {getattr(ti, 'try_number', '?')}",
        f"Log:     {ui}/dags/{dag_id}/runs/{run_id}/tasks/{task_id}",
        "",
        f"Error: {context.get('exception')}",
    ]
    if task_id.startswith("dbt"):
        artifact = "sources.json" if "freshness" in task_id else "run_results.json"
        failed = dbt_failures(artifact=artifact)
        if failed:
            lines += ["", "Failed dbt nodes:", *failed]
    return f"[dublinbikes] {dag_id}.{task_id} failed", "\n".join(lines)


def notify_failure(context: dict) -> None:
    """Airflow on_failure_callback. Never raises: a broken alert must not mask the real error."""
    try:
        send_email(*build_failure_message(context))
    except Exception as e:
        logger.error(f"Failed to send failure alert: {e}", exc_info=True)
