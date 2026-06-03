"""
send_email.py
Sends the research briefing email via Gmail SMTP (smtp.gmail.com, port 587).

Reads credentials from environment variables:
  SMTP_USER        — Gmail address used to send
  SMTP_PASSWORD    — Gmail app password
  RECIPIENT_EMAIL  — Destination address

Modes:
  success       — Attaches the generated PDF; body lists paper count,
                  subtopics covered, and a flagged-papers note if applicable.
  no-new-papers — Notifies that all papers were already seen in a prior run.
  failure       — Notifies that the pipeline failed and names the broken step.
"""

import argparse
import json
import os
import smtplib
import sys
from datetime import date
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def build_message(smtp_user: str, recipient: str, subject: str, body: str,
                  attachments: list | None = None) -> MIMEMultipart:
    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for path in (attachments or []):
        path = Path(path)
        if path.exists():
            with open(path, "rb") as f:
                part = MIMEApplication(f.read(), Name=path.name)
            part["Content-Disposition"] = f'attachment; filename="{path.name}"'
            msg.attach(part)
            print(f"  Attached: {path.name}")
        else:
            print(f"  WARNING: attachment not found: {path}")

    return msg


def send(msg: MIMEMultipart, smtp_user: str, smtp_password: str, recipient: str) -> None:
    print(f"Connecting to {SMTP_HOST}:{SMTP_PORT}...")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
    print(f"Email sent to {recipient}.")


def get_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"ERROR: environment variable {name} is not set")
        sys.exit(1)
    return value


def main():
    parser = argparse.ArgumentParser(description="Send research briefing email")
    parser.add_argument("--mode", choices=["success", "no-new-papers", "failure"],
                        required=True)
    parser.add_argument("--run-dir", default=None,
                        help="Run folder (required for success mode)")
    parser.add_argument("--date", default=str(date.today()),
                        help="Run date in YYYY-MM-DD format")
    parser.add_argument("--failed-step", default="unknown step",
                        help="Name of the step that failed (failure mode)")
    args = parser.parse_args()

    smtp_user = get_env("SMTP_USER")
    smtp_password = get_env("SMTP_PASSWORD")
    recipient = get_env("RECIPIENT_EMAIL")
    run_date = args.date

    # ── no-new-papers ─────────────────────────────────────────────────────────
    if args.mode == "no-new-papers":
        subject = f"Research Briefing — {run_date} — No new papers today"
        body = (
            f"Research Briefing — {run_date}\n\n"
            "No new papers were found today. All papers returned by today's search "
            "have already been included in a previous briefing.\n\n"
            "The daily briefing will resume automatically when new papers become available."
        )
        msg = build_message(smtp_user, recipient, subject, body)

    # ── failure ───────────────────────────────────────────────────────────────
    elif args.mode == "failure":
        subject = f"Research Briefing — {run_date} — PIPELINE FAILED"
        body = (
            f"Research Briefing — {run_date}\n\n"
            f"The automated pipeline failed at: {args.failed_step}\n\n"
            "Please check the GitHub Actions run logs for the full error trace. "
            "No briefing PDF was generated for today.\n\n"
            "Common causes:\n"
            "  • Expired or missing API key (ANTHROPIC_API_KEY, FIRECRAWL_API_KEY)\n"
            "  • Semantic Scholar rate limit exceeded\n"
            "  • Research proposal PDF missing from the repository\n"
        )
        msg = build_message(smtp_user, recipient, subject, body)

    # ── success ───────────────────────────────────────────────────────────────
    elif args.mode == "success":
        if not args.run_dir:
            print("ERROR: --run-dir is required for success mode")
            sys.exit(1)

        run_dir = Path(args.run_dir)

        # Read summary stats
        summarized_path = run_dir / "papers_summarized.json"
        flagged_path = run_dir / "flagged_papers.json"

        papers: list = []
        subtopics: list[str] = []
        flagged_count = 0

        if summarized_path.exists():
            data = json.loads(summarized_path.read_text(encoding="utf-8"))
            # papers_summarized.json is a list; coherence_changes may be appended as a key
            paper_list = [p for p in data if isinstance(p, dict) and p.get("title")]
            papers = paper_list
            subtopics = sorted(set(
                p.get("subtopic", "Uncategorized")
                for p in papers
                if p.get("subtopic")
            ))
        else:
            print("WARNING: papers_summarized.json not found; stats will be unavailable.")

        if flagged_path.exists():
            flagged_data = json.loads(flagged_path.read_text(encoding="utf-8"))
            flagged_count = len(flagged_data) if isinstance(flagged_data, list) else 0

        n = len(papers)
        subject = f"\U0001f4c4 Research Briefing — {run_date} — {n} new papers"

        subtopics_str = (
            "\n".join(f"  • {t}" for t in subtopics)
            if subtopics else "  (subtopic data unavailable)"
        )
        flagged_note = ""
        if flagged_count > 0:
            flagged_note = (
                f"\n⚠️  {flagged_count} paper(s) flagged for potentially weak summaries "
                "(see flagged_papers.json in the run folder for details).\n"
            )

        body = (
            f"Research Briefing — {run_date}\n\n"
            f"{n} new paper(s) found and summarized.\n\n"
            f"Subtopics covered:\n{subtopics_str}\n"
            f"{flagged_note}\n"
            "The full research digest PDF is attached."
        )

        # Find PDF attachment
        pdf_files = sorted(run_dir.glob("*.pdf"))
        if not pdf_files:
            body += (
                "\n\n⚠️  PDF attachment not found in the run folder. "
                "Check the GitHub Actions logs — the generate_pdf step may have failed silently."
            )
            print("WARNING: No PDF found in run folder — sending without attachment.")

        msg = build_message(smtp_user, recipient, subject, body, attachments=pdf_files[:1])

    send(msg, smtp_user, smtp_password, recipient)


if __name__ == "__main__":
    main()
