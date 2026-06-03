# Research Briefing Agent

An automated research paper digest that runs every morning and delivers a formatted PDF to your inbox. Built on the WAT framework (Workflows, Agents, Tools).

## What it does

Every day at 8am UTC the pipeline:

1. Parses your research proposal PDF to extract subtopics and cited papers
2. Searches Semantic Scholar for relevant papers (seed papers by DOI + keyword discovery per subtopic)
3. Filters out papers already delivered in a previous briefing
4. Enriches each paper with full text via Firecrawl (falls back to abstract if unavailable)
5. Uses Claude to summarize each paper: abstract, summary, key findings, results, conclusion, and subtopic assignment
6. Generates a structured PDF digest organized by subtopic
7. Emails the PDF to you and commits the seen-papers list back to the repo so duplicates are never delivered

If no new papers are found, you get a short email saying so instead of an empty digest.
If the pipeline fails at any step, you get a failure notification naming exactly which step broke.

## Architecture

```
workflows/   — Markdown SOPs describing what to do and how (the instructions)
tools/       — Python scripts that do the actual work (deterministic execution)
.github/     — GitHub Actions workflow for daily automation
assets/      — Research proposal PDF used as the source of truth
seen_papers.json — Persistent memory: paperIds already delivered (auto-committed by CI)
```

The agent layer (Claude Code or GitHub Actions) reads the workflow, calls the tools in sequence, and handles failures. Probabilistic reasoning stays in the agent; deterministic execution stays in the scripts.

## Tools

| Script | What it does |
|--------|-------------|
| `parse_proposal.py` | Extracts subtopics and cited papers from the proposal PDF using Claude |
| `search_papers.py` | Fetches cited papers by DOI + keyword search per subtopic via Semantic Scholar |
| `filter_seen_papers.py` | Removes already-seen papers; updates persistent memory after a successful run |
| `scrape_paper_content.py` | Enriches papers with full text via Firecrawl |
| `summarize_and_organize.py` | Summarizes each paper with Claude and assigns it to a subtopic |
| `generate_pdf.py` | Builds the formatted PDF digest with cover page, TOC, and per-paper entries |
| `send_email.py` | Delivers the PDF via Gmail SMTP (success, no-new-papers, or failure modes) |

## Running manually

```bash
# Set a timestamped run folder
RUN=.tmp/run_$(date +%Y-%m-%d_%H%M%S)
mkdir -p $RUN

python tools/parse_proposal.py \
  --output $RUN/proposal_context.json

python tools/search_papers.py \
  --context $RUN/proposal_context.json \
  --output  $RUN/papers_raw.json \
  --total   18

python tools/scrape_paper_content.py \
  --input  $RUN/papers_raw.json \
  --output $RUN/papers_enriched.json

python tools/summarize_and_organize.py \
  --input   $RUN/papers_enriched.json \
  --context $RUN/proposal_context.json \
  --output  $RUN/papers_summarized.json

python tools/generate_pdf.py \
  --input   $RUN/papers_summarized.json \
  --context $RUN/proposal_context.json \
  --output  $RUN/research_digest_$(date +%Y-%m-%d).pdf
```

Copy `.env.example` to `.env` and fill in your API keys before running locally.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude API — used for parsing and summarization |
| `FIRECRAWL_API_KEY` | Full-text scraping (optional; falls back to abstracts) |
| `SMTP_USER` | Gmail address that sends the briefing |
| `SMTP_PASSWORD` | Gmail app password (not your account password) |
| `RECIPIENT_EMAIL` | Where the briefing is delivered |

For the automated GitHub Action these are stored as repository secrets. For local runs they go in `.env` (gitignored).

## Triggering a manual run via GitHub Actions

Go to **Actions → Daily Research Briefing → Run workflow → Run workflow**.
