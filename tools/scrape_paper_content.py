"""
scrape_paper_content.py
Enriches each paper with full text scraped via Firecrawl.
Priority: arXiv HTML page > DOI landing page > Semantic Scholar page
Falls back to abstract-only if scraping fails or returns thin content.

Output: .tmp/papers_enriched.json
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from firecrawl import FirecrawlApp
from dotenv import load_dotenv

load_dotenv()

MIN_CONTENT_CHARS = 300  # below this, treat scrape as failed


def build_scrape_urls(paper: dict) -> list[str]:
    """Return candidate URLs to try, in priority order."""
    urls = []
    doi = paper.get("doi") or ""
    url = paper.get("url") or ""

    # arXiv HTML page (richest for arXiv papers)
    if "arxiv.org/abs/" in url:
        arxiv_id = url.split("arxiv.org/abs/")[-1].split("v")[0]
        urls.append(f"https://arxiv.org/html/{arxiv_id}")
        urls.append(url)  # fallback to abstract page
    elif doi.startswith("arXiv:"):
        arxiv_id = doi.replace("arXiv:", "")
        urls.append(f"https://arxiv.org/html/{arxiv_id}")
        urls.append(f"https://arxiv.org/abs/{arxiv_id}")

    # DOI landing page
    if doi and not doi.startswith("arXiv:"):
        urls.append(f"https://doi.org/{doi}")

    # Semantic Scholar page as last resort
    if url and url not in urls:
        urls.append(url)

    return urls


def scrape_with_firecrawl(app: FirecrawlApp, url: str) -> str | None:
    try:
        result = app.scrape_url(url, formats=["markdown"])
        if result is None:
            return None
        # firecrawl-py v2 returns a Document object; older versions returned a dict
        if isinstance(result, dict):
            content = result.get("markdown", "") or ""
        else:
            content = getattr(result, "markdown", "") or ""
        content = content.strip()
        if len(content) >= MIN_CONTENT_CHARS:
            return content
        return None
    except Exception as e:
        print(f"    Firecrawl error for {url}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=".tmp/papers_raw.json")
    parser.add_argument("--output", default=".tmp/papers_enriched.json")
    args = parser.parse_args()

    papers = json.loads(Path(args.input).read_text(encoding="utf-8"))

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        print("ERROR: FIRECRAWL_API_KEY not set in .env")
        # Graceful degradation: copy abstract as full_text and continue
        for p in papers:
            p["full_text"] = p.get("abstract", "")
        Path(args.output).write_text(json.dumps(papers, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved (abstract-only fallback) to {args.output}")
        return

    app = FirecrawlApp(api_key=api_key)
    enriched = 0

    print(f"Scraping content for {len(papers)} papers...")
    for i, paper in enumerate(papers, 1):
        title = paper.get("title", "")[:60]
        print(f"  [{i}/{len(papers)}] {title}")

        candidates = build_scrape_urls(paper)
        full_text = None

        for url in candidates:
            if not url:
                continue
            print(f"    Trying: {url[:80]}")
            full_text = scrape_with_firecrawl(app, url)
            if full_text:
                print(f"    Got {len(full_text)} chars")
                enriched += 1
                break
            time.sleep(1)  # rate limit between attempts

        paper["full_text"] = full_text or paper.get("abstract", "")
        time.sleep(1)  # rate limit between papers

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(papers, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nEnriched {enriched}/{len(papers)} papers with full text")
    print(f"Saved to {output_path}")


if __name__ == "__main__":
    main()
