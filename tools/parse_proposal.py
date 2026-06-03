"""
parse_proposal.py
Reads a research proposal PDF and extracts structured context:
  - Research title, question, aims
  - Subtopics (for organizing papers)
  - Cited papers with DOIs/URLs

Output: .tmp/proposal_context.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import anthropic
from pypdf import PdfReader
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """You are a research assistant. You will be given the full text of a research proposal.
Extract and return a JSON object with exactly this structure:

{
  "title": "full title of the research",
  "author": "author name",
  "research_question": "the main research question",
  "aims": ["aim 1", "aim 2", ...],
  "subtopics": [
    {"name": "subtopic label", "description": "brief description of what papers in this subtopic cover"},
    ...
  ],
  "cited_papers": [
    {"title": "paper title", "authors": "author names", "year": 2023, "doi": "10.xxxx/xxxxx", "url": "https://..."},
    ...
  ]
}

For subtopics: derive 3–5 meaningful categories that group the research themes (e.g., model architectures,
explainability methods, ecological context, dataset/tools). These will be used to organize found papers.

For cited_papers: extract every reference. Use null for doi or url if not present.
For arXiv papers, put the full arXiv URL in the url field and extract the arXiv ID into doi as "arXiv:XXXX.XXXXX".

Return only valid JSON, no markdown fences."""


def extract_pdf_text(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def parse_proposal(pdf_path: str) -> dict:
    print(f"Reading PDF: {pdf_path}")
    text = extract_pdf_text(pdf_path)
    print(f"Extracted {len(text)} characters from PDF")

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    print("Sending to Claude for structured extraction...")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"Here is the research proposal text:\n\n{text}"}
        ],
    )

    raw = response.content[0].text.strip()

    # Strip markdown fences if Claude added them despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Claude returned invalid JSON: {e}")
        print("Raw response:", raw[:500])
        sys.exit(1)

    return data


def main():
    parser = argparse.ArgumentParser(description="Parse research proposal PDF into structured JSON")
    parser.add_argument(
        "--pdf",
        default="assets/Research Proposal Draft Marcelo Cardenas Leal.pdf",
        help="Path to the proposal PDF",
    )
    parser.add_argument("--output", default=".tmp/proposal_context.json")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"ERROR: PDF not found at {pdf_path}")
        sys.exit(1)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = parse_proposal(str(pdf_path))

    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved proposal context to {output_path}")
    print(f"  Title: {data.get('title', 'N/A')}")
    print(f"  Subtopics: {len(data.get('subtopics', []))}")
    print(f"  Cited papers: {len(data.get('cited_papers', []))}")


if __name__ == "__main__":
    main()
