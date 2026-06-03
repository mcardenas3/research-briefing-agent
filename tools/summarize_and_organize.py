"""
summarize_and_organize.py
For each paper, uses Claude to produce:
  - summary (2-3 sentences)
  - findings (bullet list)
  - results (metrics/outcomes)
  - conclusion (1-2 sentences)
  - subtopic (assigned to one of the proposal's subtopics)

Uses prompt caching on the system prompt to reduce cost.
Output: .tmp/papers_summarized.json
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import anthropic
from dotenv import load_dotenv

load_dotenv()

MAX_TEXT_CHARS = 8000  # truncate full_text to keep token cost manageable


def build_system_prompt(subtopics: list[dict], research_title: str) -> str:
    subtopic_list = "\n".join(
        f"- \"{s['name']}\": {s.get('description', '')}" for s in subtopics
    )
    return f"""You are a research assistant helping a student understand papers related to their dissertation.

Dissertation title: "{research_title}"

For each paper provided, return a JSON object with exactly these fields:
{{
  "summary": "2-3 sentence overview of what the paper is about and its main contribution",
  "findings": ["key finding 1", "key finding 2", "key finding 3"],
  "results": "specific metrics, accuracy numbers, or outcomes reported (e.g. '98.3% accuracy on test set'). If no specific metrics, describe the key result qualitatively.",
  "conclusion": "1-2 sentence conclusion or takeaway from the paper",
  "subtopic": "exact name of the most relevant subtopic from the list below"
}}

Available subtopics (assign exactly one):
{subtopic_list}

Return only valid JSON, no markdown fences, no extra text."""


def summarize_paper(client: anthropic.Anthropic, paper: dict, system_prompt: str) -> dict:
    text = paper.get("full_text") or paper.get("abstract") or ""
    text = text[:MAX_TEXT_CHARS]

    user_content = f"""Title: {paper.get('title', '')}
Authors: {paper.get('authors', '')}
Year: {paper.get('year', '')}

Content:
{text}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Return a safe fallback so the pipeline doesn't crash
        return {
            "summary": text[:300] + "..." if len(text) > 300 else text,
            "findings": ["See abstract for details"],
            "results": "Not extracted",
            "conclusion": "See paper for conclusions",
            "subtopic": "Uncategorized",
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=".tmp/papers_enriched.json")
    parser.add_argument("--context", default=".tmp/proposal_context.json")
    parser.add_argument("--output", default=".tmp/papers_summarized.json")
    args = parser.parse_args()

    papers = json.loads(Path(args.input).read_text(encoding="utf-8"))
    context = json.loads(Path(args.context).read_text(encoding="utf-8"))

    subtopics = context.get("subtopics", [])
    title = context.get("title", "Research Digest")

    if not subtopics:
        print("WARNING: No subtopics found in proposal context. Papers will be uncategorized.")

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    system_prompt = build_system_prompt(subtopics, title)

    print(f"Summarizing {len(papers)} papers with Claude Haiku...")
    for i, paper in enumerate(papers, 1):
        print(f"  [{i}/{len(papers)}] {paper.get('title', '')[:70]}")

        summary_data = summarize_paper(client, paper, system_prompt)
        paper.update(summary_data)

        time.sleep(0.3)  # gentle rate limiting

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(papers, indent=2, ensure_ascii=False), encoding="utf-8")

    subtopic_counts = {}
    for p in papers:
        st = p.get("subtopic", "Uncategorized")
        subtopic_counts[st] = subtopic_counts.get(st, 0) + 1

    print(f"\nSaved to {output_path}")
    print("Papers per subtopic:")
    for st, count in subtopic_counts.items():
        print(f"  {st}: {count}")


if __name__ == "__main__":
    main()
