# Workflow: Research Paper Summary PDF

## Objective
Generate a structured PDF digest of academic papers relevant to the user's research proposal. Each paper is summarized (abstract, summary, key findings, results, conclusion, link) and organized by subtopics derived from the proposal. Unlike a fixed pipeline, this workflow uses agent judgment at four checkpoints to catch coverage gaps, size the collection appropriately, flag weak summaries, and verify groupings before producing the final PDF.

## Required Inputs
- Research proposal PDF (default: `assets/Research Proposal Draft Marcelo Cardenas Leal.pdf`)

## Required Environment Variables (`.env`)
- `ANTHROPIC_API_KEY` — for Claude-based parsing, summarization, and agent evaluation steps
- `FIRECRAWL_API_KEY` — for scraping full paper text (optional; falls back to abstracts)

## Output
`.tmp/<run_folder>/research_digest_YYYY-MM-DD.pdf`

All intermediate files and the final PDF for a single run are stored together in one subfolder under `.tmp/`. This keeps multiple runs isolated from each other.

---

## Steps

### Step 0 — Create Run Folder and Parse Proposal PDF

**First**, before running any tool, create a timestamped run folder to hold all files produced by this run:

```
run_folder = .tmp/run_YYYY-MM-DD_HHMMSS   (e.g. .tmp/run_2026-06-03_143022)
```

Create this directory, then pass `--output-dir <run_folder>` to every tool command in this workflow. All `.json` intermediates and the final `.pdf` go inside this folder — nothing goes directly into `.tmp/`.

```
python tools/parse_proposal.py --pdf "assets/Research Proposal Draft Marcelo Cardenas Leal.pdf" --output-dir .tmp/run_YYYY-MM-DD_HHMMSS
```
**Output:** `.tmp/<run_folder>/proposal_context.json`
**Checks:** Must have `subtopics` (3–5 items) and `cited_papers` (should find ~10).

**Edge case:** If fewer than 3 subtopics are extracted, re-run with a note to Claude to infer more granular categories from the objectives section.

---

### Step 0.5 — Determine Target Paper Count (Agent Decision)

Before running any searches, reason about how many papers are appropriate. Do not use a hardcoded number. Instead, inspect `<run_folder>/proposal_context.json` and apply the following logic:

**Formula:**
```
base_count = subtopic_count * 4
complexity_bonus = 2 if cited_papers_in_proposal > 15 else 0
complexity_bonus += 2 if research_question_word_count > 80 else 0
target = max(12, min(base_count + complexity_bonus, 25))
```

**How to apply this:**
1. Read `subtopics` length from `<run_folder>/proposal_context.json`
2. Read `cited_papers` length and estimate `research_question_word_count` from the `research_question` field
3. Compute `target` using the formula above
4. Write `target` into `<run_folder>/proposal_context.json` under the key `"target_paper_count"` so downstream steps can read it

**Example reasoning:**
- 4 subtopics, 12 cited papers, short research question → `4*4 + 0 = 16`
- 5 subtopics, 20 cited papers, long research question → `5*4 + 4 = 24`
- 3 subtopics, 8 cited papers → `3*4 = 12` (floor kicks in)

**Edge cases:**
- If `subtopics` is missing or empty, default to 18 and log a warning
- If the formula produces a number below 12 (unlikely but possible), floor it at 12
- Do not exceed 25 — beyond that, summarization cost and PDF length degrade quality

Pass the computed value as `--total` in Step 1:
```
python tools/search_papers.py --total <computed_target> --output-dir .tmp/<run_folder>
```

---

### Step 1 — Search and Collect Papers
```
python tools/search_papers.py --total <target_paper_count> --output-dir .tmp/<run_folder>
```
**Output:** `.tmp/<run_folder>/papers_raw.json`
**Checks:** Should have papers close to `target_paper_count`, all with non-empty `abstract`.

**Edge cases:**
- DOI not found on Semantic Scholar → script falls back to title search automatically
- Fewer than 10 papers found → proceed to the coverage gate below before widening manually
- Duplicate papers → deduplicated by `paperId` automatically

---

### Step 1.5 — Coverage Quality Gate (Agent Decision, up to 3 attempts)

After Step 1, evaluate whether the collected papers actually cover all subtopics from `proposal_context.json`. Do not skip this step even if the paper count looks fine — count alone does not guarantee coverage.

**How to evaluate:**
1. Read `<run_folder>/papers_raw.json` and `<run_folder>/proposal_context.json`
2. For each subtopic, count how many papers have that subtopic keyword (or close synonym) in their title or abstract
3. A subtopic is "covered" if it has at least 2 papers; "thin" if it has 1; "missing" if it has 0

**Decision logic:**
- If all subtopics are covered → proceed to Step 2
- If any subtopic is thin or missing → refine the search queries and re-run Step 1 with adjusted terms (see below), then re-evaluate. Repeat up to **3 total attempts**.
- After 3 attempts, if gaps remain → proceed anyway but log which subtopics are undercovered in `<run_folder>/coverage_report.json` so the user is aware

**How to refine queries between attempts:**
- Attempt 2: Broaden by adding synonyms or related terms to the thin subtopic's search query. For example, if "transfer learning in NLP" has no results, also try "domain adaptation" and "fine-tuning language models".
- Attempt 3: If attempt 2 still fails, relax the year filter (if any) and try title-only search instead of full-text.

To re-run with adjusted subtopics, edit the relevant entries in `<run_folder>/proposal_context.json` and call:
```
python tools/search_papers.py --total <target_paper_count> --output-dir .tmp/<run_folder>
```

**Edge cases:**
- If the proposal has only 3 subtopics and one is very niche, 1 paper may be the realistic ceiling — accept this and note it
- Do not inflate coverage by reassigning papers from well-covered subtopics; that creates false gaps elsewhere
- Log each attempt's subtopic coverage counts in `<run_folder>/coverage_report.json` so you can compare across attempts

---

### Step 2 — Enrich with Full Text (Firecrawl)
```
python tools/scrape_paper_content.py --output-dir .tmp/<run_folder>
```
**Output:** `.tmp/<run_folder>/papers_enriched.json`
**Checks:** At least some papers should have `full_text` longer than 300 chars.

**Edge cases:**
- Firecrawl rate limit or error → script skips that URL and tries the next candidate; falls back to abstract
- No `FIRECRAWL_API_KEY` → all papers use abstract as `full_text` (still works, just less detailed summaries)
- ArXiv HTML page not available (older papers) → falls back to arXiv abstract page

---

### Step 3 — Summarize and Organize
```
python tools/summarize_and_organize.py --output-dir .tmp/<run_folder>
```
**Output:** `.tmp/<run_folder>/papers_summarized.json`
**Checks:** Every paper must have `abstract`, `summary`, `findings` (list), `results`, `conclusion`, and `subtopic`.

The `abstract` field must be carried through from `papers_enriched.json` unchanged — do not overwrite it with the generated summary. It is displayed separately in the PDF as the original author-written abstract.

**Edge cases:**
- Claude returns invalid JSON → script uses a safe fallback (abstract as summary) and continues
- Paper has no abstract from the source → leave `abstract` as `""` so the PDF can display "Abstract not available"
- Paper assigned to "Uncategorized" → acceptable; it will appear in its own section in the PDF
- Cost concern: uses Claude Haiku with prompt caching; ~18 papers costs < $0.05

---

### Step 3.5 — Summary Quality Self-Evaluation (Agent Decision)

After Step 3, review the summaries for substantiveness before moving to PDF generation. The goal is to catch papers where the script produced placeholder content rather than a real summary.

**How to evaluate:**
1. Read `<run_folder>/papers_summarized.json`
2. For each paper, check:
   - `summary` is longer than 80 characters and is not the raw abstract copy-pasted verbatim
   - `findings` has at least 2 non-empty items
   - `results` is not `"N/A"`, `"None"`, `""`, or a close variant
   - `conclusion` is not `"N/A"`, `"None"`, `""`, or a close variant

**Decision logic:**
- Papers that fail 2 or more of the above checks are flagged as **placeholder candidates**
- Write flagged papers to `<run_folder>/flagged_papers.json` with the specific fields that failed and a short reason
- Print a clear warning listing each flagged paper's title so the user can review before continuing
- Do not stop the workflow — proceed to Step 4 with the full set. The flag file is for manual review.

**Example warning output:**
```
[WARNING] 3 papers have weak summaries and are flagged for review:
  - "Attention Is All You Need" → results field is "N/A", findings has only 1 item
  - "BERT: Pre-training..." → summary appears to be raw abstract (similarity > 0.95)
  - "On the Measure of..." → all fields are single-sentence placeholders
See .tmp/<run_folder>/flagged_papers.json for details.
```

**Edge cases:**
- If more than 30% of papers are flagged, that suggests a systemic issue (e.g., Firecrawl returned nothing for most papers). In that case, ask the user whether to re-run Step 2 with a different scraping strategy before generating the PDF.
- If zero papers are flagged, skip writing `flagged_papers.json` and continue silently
- Do not re-run summarization automatically — it has API cost. Surface the flags and let the user decide.

---

### Step 4 — Coherence Check (Agent Decision)

Before generating the PDF, verify that the subtopic groupings make sense. Misclassified papers create a confusing digest that undermines the whole output.

**How to evaluate:**
1. Read `<run_folder>/papers_summarized.json` and the subtopic list from `<run_folder>/proposal_context.json`
2. For each paper, read its `summary` and `findings` and ask: does this paper genuinely belong to its assigned `subtopic`?
3. Flag any paper where the content clearly better fits a different subtopic

**Decision logic:**
- If a paper's summary and findings have no meaningful overlap with its assigned subtopic's theme, reassign it to the best-fit subtopic from the list
- If no subtopic fits, leave the paper in "Uncategorized" rather than forcing a bad match
- After reassignment, re-check that each subtopic still has at least 1 paper; if a subtopic has been emptied out, note this in a warning

**How to reassign:**
Directly edit `<run_folder>/papers_summarized.json`, updating the `subtopic` field for affected papers. Do not re-run any tool scripts — this is a pure agent reasoning step operating on the JSON file.

**Log the changes:**
Append a `"coherence_changes"` key to `<run_folder>/papers_summarized.json` listing each reassignment:
```json
"coherence_changes": [
  {
    "paper_id": "abc123",
    "title": "...",
    "from_subtopic": "Transfer Learning",
    "to_subtopic": "Evaluation Benchmarks",
    "reason": "Paper focuses on benchmark construction, not transfer methodology"
  }
]
```

**Edge cases:**
- If you find yourself reassigning more than 4 papers, that suggests `parse_proposal.py` produced poorly defined subtopics. Note this and consider re-running Step 0 with a prompt refinement before continuing.
- Do not reassign a paper just because it's tangentially related to multiple subtopics — only move it if the current assignment is clearly wrong
- Papers in "Uncategorized" are not evaluated in this step; they stay there by design

---

### Step 5 — Generate PDF
```
python tools/generate_pdf.py --output-dir .tmp/<run_folder>
```
**Output:** `.tmp/<run_folder>/research_digest_YYYY-MM-DD.pdf`
**Checks:** Open PDF and verify:
- Cover page shows title, author, date, research question
- Table of contents lists all subtopics and paper titles
- Each paper entry displays: **Abstract** (original author text), then **Summary**, **Key Findings**, **Results**, **Conclusion**, and a clickable link — in that order
- Abstract section is visually distinct from the agent-generated summary (e.g., italicized or labeled "Author Abstract")
- No garbled text or encoding errors
- If `<run_folder>/flagged_papers.json` exists, check that those papers are still useful enough to include — remove any that are purely placeholder if needed before this step

---

## Full Pipeline (single command sequence)

Steps 0.5, 1.5, 3.5, and 4 are **agent reasoning steps** — they do not have tool commands. The runnable commands in order are:

```bash
# Set run folder once at the start (substitute actual timestamp)
RUN=.tmp/run_YYYY-MM-DD_HHMMSS
mkdir -p $RUN

python tools/parse_proposal.py \
  --output $RUN/proposal_context.json

# [Agent: compute target_paper_count, write to proposal_context.json]

python tools/search_papers.py \
  --context $RUN/proposal_context.json \
  --output  $RUN/papers_raw.json \
  --total   <target>

# [Agent: run coverage gate; re-run search up to 2 more times if gaps exist]

python tools/scrape_paper_content.py \
  --input  $RUN/papers_raw.json \
  --output $RUN/papers_enriched.json

python tools/summarize_and_organize.py \
  --input   $RUN/papers_enriched.json \
  --context $RUN/proposal_context.json \
  --output  $RUN/papers_summarized.json

# [Agent: run summary quality check; write flagged_papers.json if needed]
# [Agent: run coherence check; reassign papers in papers_summarized.json if needed]

python tools/generate_pdf.py \
  --input   $RUN/papers_summarized.json \
  --context $RUN/proposal_context.json \
  --output  $RUN/research_digest_YYYY-MM-DD.pdf
```

## Re-running Individual Steps
Each step reads from and writes to the same `<run_folder>`. You can re-run any step independently after fixing an issue without re-running the whole pipeline. For example, to re-generate just the PDF:
```bash
RUN=.tmp/run_2026-06-03_143022

python tools/generate_pdf.py \
  --input   $RUN/papers_summarized.json \
  --context $RUN/proposal_context.json \
  --output  $RUN/research_digest_2026-06-03.pdf
```

To start a completely fresh run (new search, new summaries), create a new timestamped folder at Step 0. Old runs remain untouched in their own subfolders.

## Files Produced Per Run
All 10 files for a run live inside `.tmp/<run_folder>/`:

| File | Produced by |
|------|-------------|
| `proposal_context.json` | Step 0 + Step 0.5 |
| `papers_raw.json` | Step 1 |
| `coverage_report.json` | Step 1.5 (if gaps found) |
| `papers_enriched.json` | Step 2 |
| `papers_summarized.json` | Step 3 + Step 4 |
| `flagged_papers.json` | Step 3.5 (if issues found) |
| `research_digest_YYYY-MM-DD.pdf` | Step 5 |

Example layout after two runs:
```
.tmp/
  run_2026-06-03_090012/
    proposal_context.json
    papers_raw.json
    papers_enriched.json
    papers_summarized.json
    research_digest_2026-06-03.pdf
  run_2026-06-03_154530/
    proposal_context.json
    papers_raw.json
    coverage_report.json
    papers_enriched.json
    papers_summarized.json
    flagged_papers.json
    research_digest_2026-06-03.pdf
```

## Notes / Lessons Learned

**Original pipeline lessons:**
- Semantic Scholar's free API has a rate limit of ~100 requests/minute; the scripts sleep 0.5–1s between calls to stay well within it
- ArXiv HTML pages (`arxiv.org/html/<id>`) return the richest text for open-access papers; always try these first
- Firecrawl works best on arXiv and Semantic Scholar pages; DOI landing pages often redirect to paywalled content with thin text
- If a paper has no abstract and Firecrawl returns nothing, the summarization step still runs but produces a placeholder — the self-evaluation step (3.5) now catches these automatically

**Why this version is more agentic:**

The original workflow was a linear pipeline: run five commands in sequence, check counts, done. It treated success as "all steps completed" rather than "the output is actually good." Four agent decision points were added to change that:

1. **Dynamic paper count (Step 0.5):** A hardcoded `--total 18` assumes every research question has the same scope. A proposal with 5 subtopics and 20 cited papers warrants more coverage than one with 3 subtopics and 8. The formula makes this reasoning explicit and repeatable instead of leaving it to whoever runs the workflow.

2. **Coverage quality gate (Step 1.5):** Paper count is a proxy metric. A collection of 18 papers all about the same subtopic technically passes the count check but fails at its actual purpose. The gate catches this by evaluating coverage per subtopic and iterating with refined queries — up to 3 attempts — before falling back to a documented warning. This mirrors how a researcher would actually review search results before moving on.

3. **Summary self-evaluation (Step 3.5):** The summarization tool is reliable but degrades when input text is thin (no abstract, Firecrawl returned nothing). Without this gate, placeholder summaries silently end up in the PDF. The evaluation step surfaces these as named flags so the user can decide whether to intervene — without re-running summarization automatically (which has cost).

4. **Coherence check (Step 4):** The `summarize_and_organize.py` tool assigns subtopics based on keyword proximity, which can misclassify papers that use different terminology for related concepts. A final agent review of the assignments — with direct JSON edits and a logged audit trail — ensures the PDF groupings reflect actual content rather than surface-level matches.

**Abstract in PDF (added):** Each paper entry in the PDF now shows the original author-written abstract before the agent-generated summary. These serve different purposes: the abstract is the authors' own framing; the summary is the agent's synthesis oriented toward the research proposal. Keeping both lets the reader verify the agent's interpretation against the source.

**Per-run subfolders (added):** All files including the final PDF are written to `.tmp/run_YYYY-MM-DD_HHMMSS/` rather than flat into `.tmp/`. This means multiple runs never overwrite each other, old runs can be compared or referenced, and cleanup is as simple as deleting a single folder. Every tool command accepts `--input`/`--output` pointing into this folder; always pass them explicitly.

---

## Automation

### How the GitHub Action works

The workflow is defined in `.github/workflows/daily_research_briefing.yml`. It runs the five deterministic tool scripts in sequence (Steps 0, 1, 2, 3, 5), skipping the agent reasoning steps (0.5, 1.5, 3.5, 4) which require interactive judgment. The default `--total 18` is used for the paper search.

Before each tool step, the action sets a `CURRENT_STEP` environment variable. If any step fails, the final "Send failure notification" step reads this variable to report exactly where the pipeline broke.

Full execution order:
1. Parse proposal → `proposal_context.json`
2. Search papers → `papers_raw.json`
3. Filter seen papers (remove already-delivered papers) → filtered `papers_raw.json`
4. *(if 0 new papers)* Send "no new papers" email and stop
5. Enrich with full text → `papers_enriched.json`
6. Summarize and organize → `papers_summarized.json`
7. Generate PDF → `research_digest_YYYY-MM-DD.pdf`
8. Update `seen_papers.json` and commit it back to the repo
9. Send briefing email with PDF attachment

### GitHub secrets required

| Secret | Purpose |
|--------|---------|
| `ANTHROPIC_API_KEY` | Claude API — used by `parse_proposal.py` and `summarize_and_organize.py` |
| `FIRECRAWL_API_KEY` | Firecrawl scraping — used by `scrape_paper_content.py` (optional; falls back to abstracts if absent) |
| `SMTP_USER` | Gmail address that sends the briefing emails |
| `SMTP_PASSWORD` | Gmail app password (not your regular Gmail password — generate one at myaccount.google.com/apppasswords) |
| `RECIPIENT_EMAIL` | Email address that receives the briefing |

### How seen_papers.json memory works across runs

`seen_papers.json` lives in the repository root and contains a JSON array of `paperIds` that have already been delivered in a prior briefing. It is **not** in `.gitignore` and is committed back to the repo after each successful run by the `github-actions[bot]`.

- **Filter step** (`tools/filter_seen_papers.py --mode filter`): runs after Step 1, removes any paper whose `paperId` is already in `seen_papers.json`, and overwrites `papers_raw.json` with the filtered list. Also saves new IDs to `<run_folder>/new_paper_ids.json` for the update step.
- **Update step** (`tools/filter_seen_papers.py --mode update`): runs after a successful pipeline, appends the new paper IDs to `seen_papers.json`, which is then committed so the next run starts with an updated memory.
- If `seen_papers.json` does not exist (first run), the filter step creates it as an empty list.

### How to trigger a manual run

From the GitHub repository, go to **Actions → Daily Research Briefing → Run workflow**. Select the branch and click **Run workflow**. This uses the `workflow_dispatch` trigger and runs the exact same pipeline as the scheduled cron job.
