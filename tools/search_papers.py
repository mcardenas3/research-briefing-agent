"""
search_papers.py
Two-phase paper collection:
  Phase A: Fetch each cited paper from the proposal by DOI via Semantic Scholar
  Phase B: Keyword search per subtopic to discover additional papers

Output: .tmp/papers_raw.json
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

# Windows console often defaults to cp1252 — force utf-8 so Unicode titles don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SS_BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,abstract,url,year,authors,openAccessPdf,externalIds"
HEADERS = {"User-Agent": "research-digest-tool/1.0"}


def ss_get(endpoint: str, params: dict = None) -> dict | None:
    url = f"{SS_BASE}/{endpoint}"
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 404:
            return None
        elif r.status_code == 429:
            print("  Rate limited by Semantic Scholar, waiting 10s...")
            time.sleep(10)
            return ss_get(endpoint, params)
        else:
            print(f"  Semantic Scholar error {r.status_code} for {url}")
            return None
    except requests.RequestException as e:
        print(f"  Request error: {e}")
        return None


def fetch_by_doi(doi: str) -> dict | None:
    # Semantic Scholar accepts DOI:xxx, arXiv:xxx, URL:xxx as paper identifiers
    identifier = doi if doi.startswith("arXiv:") else f"DOI:{doi}"
    data = ss_get(f"paper/{identifier}", {"fields": FIELDS})
    return data


def fetch_by_title(title: str) -> dict | None:
    data = ss_get("paper/search", {"query": title, "limit": 1, "fields": FIELDS})
    if data and data.get("data"):
        return data["data"][0]
    return None


def search_by_query(query: str, limit: int = 5) -> list[dict]:
    data = ss_get("paper/search", {"query": query, "limit": limit, "fields": FIELDS})
    if data and data.get("data"):
        return data["data"]
    return []


def normalize_paper(paper: dict, subtopic_hint: str = "") -> dict:
    authors = [a.get("name", "") for a in paper.get("authors", [])]
    pdf_url = None
    if paper.get("openAccessPdf"):
        pdf_url = paper["openAccessPdf"].get("url")

    # Build canonical URL: prefer openAccessPdf, then externalIds arXiv, then SS url
    ext_ids = paper.get("externalIds") or {}
    arxiv_id = ext_ids.get("ArXiv")
    doi = ext_ids.get("DOI")

    url = paper.get("url") or ""
    if arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"

    return {
        "paperId": paper.get("paperId", ""),
        "title": paper.get("title", ""),
        "authors": ", ".join(authors[:5]) + (" et al." if len(authors) > 5 else ""),
        "year": paper.get("year"),
        "abstract": paper.get("abstract") or "",
        "url": url,
        "doi": doi or (f"arXiv:{arxiv_id}" if arxiv_id else None),
        "pdf_url": pdf_url,
        "subtopic_hint": subtopic_hint,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", default=".tmp/proposal_context.json")
    parser.add_argument("--output", default=".tmp/papers_raw.json")
    parser.add_argument("--total", type=int, default=18, help="Target total papers (seed + discovery)")
    args = parser.parse_args()

    context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    cited = context.get("cited_papers", [])
    subtopics = context.get("subtopics", [])

    papers: dict[str, dict] = {}  # paperId -> normalized paper

    # ── Phase A: Fetch seed papers by DOI / title ──────────────────────────
    print(f"\nPhase A: Fetching {len(cited)} cited papers from proposal...")
    for ref in cited:
        doi = ref.get("doi") or ""
        title = ref.get("title") or ""
        time.sleep(0.5)

        paper = None
        if doi:
            print(f"  Fetching by DOI/ID: {doi[:60]}")
            paper = fetch_by_doi(doi)

        if not paper and title:
            print(f"  Fallback title search: {title[:60]}")
            paper = fetch_by_title(title)

        if paper and paper.get("paperId"):
            norm = normalize_paper(paper)
            if norm["abstract"]:  # only include papers with abstracts
                papers[norm["paperId"]] = norm
                print(f"    OK: {norm['title'][:70]}")
        else:
            print(f"    SKIP: could not find '{title[:50]}'")

    print(f"\nSeed papers collected: {len(papers)}")

    # ── Phase B: Discovery search per subtopic ─────────────────────────────
    remaining = args.total - len(papers)
    if remaining > 0 and subtopics:
        per_subtopic = max(2, remaining // len(subtopics) + 1)
        print(f"\nPhase B: Discovering ~{per_subtopic} papers per subtopic...")

        for subtopic in subtopics:
            name = subtopic.get("name", "")
            # Use only the first 6 words of the subtopic name as query (short = better results)
            query = " ".join(name.split()[:6])
            print(f"  Searching: {query}")
            time.sleep(1.5)  # extra pause to avoid rate limits

            results = search_by_query(query, limit=per_subtopic + 3)
            added = 0
            for r in results:
                pid = r.get("paperId", "")
                if pid and pid not in papers and r.get("abstract"):
                    papers[pid] = normalize_paper(r, subtopic_hint=name)
                    added += 1
                    if added >= per_subtopic:
                        break

            print(f"    Added {added} new papers")

    result = list(papers.values())
    print(f"\nTotal papers collected: {len(result)}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved to {output_path}")


if __name__ == "__main__":
    main()
