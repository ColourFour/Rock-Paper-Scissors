from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any

from .config import AppConfig
from .practice_page import _AssetResolver, _load_question_bank, _page_numbers_text, _qa_status, _qa_warnings, _text


@dataclass(frozen=True)
class ManualReviewPageResult:
    html_path: Path
    record_count: int


@dataclass(frozen=True)
class ManualReviewMergeResult:
    output_json_path: Path
    input_record_count: int
    matched_reviews: int
    unmatched_reviews: int


def build_manual_review_page(
    question_bank_path: str | Path,
    output_dir: str | Path,
    config: AppConfig,
) -> ManualReviewPageResult:
    question_bank_path = Path(question_bank_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = _load_question_bank(question_bank_path)
    asset_resolver = _AssetResolver(output_dir, copy_assets=False, asset_dir_name="assets")

    review_records = [_manual_review_record(record, index, asset_resolver) for index, record in enumerate(records)]
    topics_by_paper = {paper: sorted(topics) for paper, topics in config.paper_family_taxonomy.items() if paper != "unknown"}

    html_path = output_dir / "index.html"
    html_path.write_text(
        _html_document(
            review_records,
            topics_by_paper,
            {
                "question_bank": str(question_bank_path),
                "generated_from": str(question_bank_path.resolve()),
            },
        ),
        encoding="utf-8",
    )
    return ManualReviewPageResult(html_path=html_path, record_count=len(review_records))


def apply_manual_review(
    question_bank_path: str | Path,
    review_json_path: str | Path,
    output_json_path: str | Path,
) -> ManualReviewMergeResult:
    question_bank_path = Path(question_bank_path)
    review_json_path = Path(review_json_path)
    output_json_path = Path(output_json_path)
    records = _load_question_bank(question_bank_path)
    reviews = _load_review_export(review_json_path)
    matched_ids: set[str] = set()

    merged_records: list[dict[str, Any]] = []
    for record in records:
        merged = dict(record)
        record_id = _record_id(record)
        review = reviews.get(record_id)
        if review:
            matched_ids.add(record_id)
            _apply_review_to_record(merged, record_id, review)
        merged_records.append(merged)

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(merged_records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return ManualReviewMergeResult(
        output_json_path=output_json_path,
        input_record_count=len(records),
        matched_reviews=len(matched_ids),
        unmatched_reviews=len(set(reviews) - matched_ids),
    )


def _manual_review_record(record: dict[str, Any], index: int, asset_resolver: _AssetResolver) -> dict[str, Any]:
    question_image = _text(record.get("question_image") or record.get("screenshot_path"))
    markscheme_image = _text(record.get("markscheme_image"))
    question_asset = _asset_payload(question_image, asset_resolver)
    markscheme_asset = _asset_payload(markscheme_image, asset_resolver)
    paper_family = _text(record.get("paper_family") or record.get("question_level_paper_family"))
    auto_topic = _text(record.get("topic") or record.get("question_level_topic"))
    auto_difficulty = _text(record.get("difficulty"))
    paper_key = _text(record.get("document_key") or record.get("paper_name") or record.get("source_pdf") or paper_family)
    paper_title = _text(record.get("paper_name") or record.get("document_key") or record.get("source_pdf") or paper_family)

    return {
        "record_id": _record_id(record),
        "record_index": index,
        "paper_key": paper_key,
        "paper_title": paper_title,
        "paper_family": paper_family,
        "paper_name": _text(record.get("paper_name")),
        "source_pdf": _text(record.get("source_pdf")),
        "question_number": _text(record.get("question_number")),
        "question_label": _text(record.get("full_question_label") or record.get("question_label") or record.get("question_number")),
        "marks_if_available": record.get("marks_if_available") or record.get("marks") or "",
        "auto_topic": auto_topic,
        "auto_difficulty": auto_difficulty,
        "manual_topic": _text(record.get("manual_topic")),
        "manual_difficulty": _text(record.get("manual_difficulty")),
        "usable": record.get("usable"),
        "crop_status": _text(record.get("crop_status")),
        "notes": _text(record.get("manual_notes") or record.get("notes")),
        "manual_reviewed": bool(record.get("manual_reviewed")),
        "manual_reviewed_at": _text(record.get("manual_reviewed_at")),
        "session": _text(record.get("session")),
        "year": _text(record.get("year")),
        "component": _text(record.get("component") or record.get("source_paper_code")),
        "document_key": _text(record.get("document_key")),
        "source_page_number": _page_numbers_text(record.get("page_numbers") or record.get("question_pages")),
        "markscheme_page_number": _page_numbers_text(record.get("markscheme_pages")),
        "qa_status": _qa_status(record),
        "qa_warnings": _qa_warnings(record),
        "review_flags": _list_text(record.get("review_flags")),
        "question_image": question_asset["src"],
        "question_image_source_path": question_image,
        "question_image_resolved_path": question_asset["resolved_path"],
        "question_image_exists": question_asset["exists"],
        "markscheme_image": markscheme_asset["src"],
        "markscheme_image_source_path": markscheme_image,
        "markscheme_image_resolved_path": markscheme_asset["resolved_path"],
        "markscheme_image_exists": markscheme_asset["exists"],
    }


def _asset_payload(path_value: str, asset_resolver: _AssetResolver) -> dict[str, Any]:
    if not path_value:
        return {"src": "", "resolved_path": "", "exists": False}
    return asset_resolver.browser_asset(path_value)


def _load_review_export(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_reviews: Any
    if isinstance(data, dict):
        raw_reviews = data.get("reviews", data)
    else:
        raw_reviews = data
    reviews: dict[str, dict[str, Any]] = {}
    if isinstance(raw_reviews, dict):
        for key, value in raw_reviews.items():
            if isinstance(value, dict):
                review = dict(value)
                review.setdefault("record_id", str(key))
                reviews[str(key)] = review
    elif isinstance(raw_reviews, list):
        for value in raw_reviews:
            if isinstance(value, dict) and value.get("record_id"):
                reviews[str(value["record_id"])] = dict(value)
    return reviews


def _apply_review_to_record(record: dict[str, Any], record_id: str, review: dict[str, Any]) -> None:
    record["manual_review_id"] = record_id
    manual_topic = _text(review.get("manual_topic"))
    manual_difficulty = _text(review.get("manual_difficulty"))
    crop_status = _text(review.get("crop_status"))
    notes = _text(review.get("notes"))
    reviewed_at = _text(review.get("reviewed_at") or review.get("manual_reviewed_at"))
    usable = review.get("usable")

    if manual_topic:
        record.setdefault("auto_topic", record.get("topic") or record.get("question_level_topic") or "")
        record["manual_topic"] = manual_topic
        record["topic"] = manual_topic
        record["question_level_topic"] = manual_topic
        record["topic_confidence"] = "manual"
        record["topic_confidence_score"] = 1.0
        record["topic_uncertain"] = False

    if manual_difficulty:
        record.setdefault("auto_difficulty", record.get("difficulty") or "")
        record["manual_difficulty"] = manual_difficulty
        record["difficulty"] = _pipeline_difficulty(manual_difficulty)
        record["difficulty_confidence"] = "manual"
        record["difficulty_uncertain"] = False

    if isinstance(usable, bool):
        record["usable"] = usable
    if crop_status:
        record["crop_status"] = crop_status
    if notes:
        record["manual_notes"] = notes
    if reviewed_at:
        record["manual_reviewed_at"] = reviewed_at
    record["manual_reviewed"] = _review_has_content(review)
    record["student_usable"] = record.get("usable") is not False and _text(record.get("crop_status")).lower() != "bad"

    flags = set(_list_text(record.get("review_flags")))
    flags.add("manual_review_applied")
    if record["student_usable"] is False:
        flags.add("manual_excluded_from_student_practice")
    record["review_flags"] = sorted(flags)


def _review_has_content(review: dict[str, Any]) -> bool:
    return any(
        [
            _text(review.get("manual_topic")),
            _text(review.get("manual_difficulty")),
            isinstance(review.get("usable"), bool),
            _text(review.get("crop_status")),
            _text(review.get("notes")),
            _text(review.get("reviewed_at") or review.get("manual_reviewed_at")),
        ]
    )


def _pipeline_difficulty(value: str) -> str:
    normalized = value.strip().lower()
    return {"medium": "average", "hard": "difficult"}.get(normalized, normalized)


def _record_id(record: dict[str, Any]) -> str:
    explicit = _text(record.get("question_id"))
    if explicit:
        return _slug(explicit)
    source = _text(record.get("document_key") or record.get("paper_name") or Path(_text(record.get("source_pdf"))).stem or record.get("source_pdf"))
    label = _text(record.get("full_question_label") or record.get("question_label") or record.get("question_number"))
    pages = _page_numbers_text(record.get("page_numbers") or record.get("question_pages"))
    image = _text(record.get("question_image") or record.get("screenshot_path"))
    return _slug("::".join(part for part in [source, label, pages, image] if part))


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._()/-]+", "-", value.strip())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:180] or "record"


def _list_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _html_document(records: list[dict[str, Any]], topics_by_paper: dict[str, list[str]], metadata: dict[str, str]) -> str:
    records_json = _safe_json(records)
    topics_json = _safe_json(topics_by_paper)
    metadata_json = _safe_json(metadata)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Manual Question Review</title>
  <style>
    :root {{
      color-scheme: light;
      --background: #f5f7f3;
      --ink: #172019;
      --muted: #5b655f;
      --line: #c9d2ca;
      --surface: #ffffff;
      --accent: #24735a;
      --accent-dark: #1b5845;
      --warn: #9a5b1a;
      --bad: #9b2f2f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--background);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }}
    main {{ width: min(1380px, calc(100% - 32px)); margin: 18px auto 48px; }}
    .topbar {{
      display: flex;
      flex-wrap: wrap;
      align-items: end;
      gap: 12px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line);
    }}
    label {{ display: grid; gap: 5px; color: var(--muted); font-size: 13px; font-weight: 700; }}
    select, button, input[type="text"], textarea {{
      border: 1px solid var(--line);
      border-radius: 8px;
      font: inherit;
    }}
    select, button, input[type="text"] {{ min-height: 38px; padding: 8px 10px; }}
    select {{ min-width: min(300px, 90vw); background: var(--surface); }}
    button {{
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
      font-weight: 700;
      cursor: pointer;
    }}
    button.secondary {{ background: var(--surface); color: var(--accent-dark); border-color: var(--line); }}
    button.danger {{ background: var(--bad); border-color: var(--bad); }}
    button:disabled {{ opacity: .48; cursor: not-allowed; }}
    .filters {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      padding: 12px 0;
      color: var(--muted);
      border-bottom: 1px solid var(--line);
    }}
    .filters label {{ display: flex; align-items: center; gap: 7px; font-weight: 600; }}
    .stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 14px 0;
    }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      padding: 6px 9px;
      color: var(--muted);
      font-size: 13px;
    }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(260px, 330px) 1fr;
      gap: 18px;
      align-items: start;
    }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .panel h2, .panel h3 {{ margin: 0 0 10px; font-size: 18px; }}
    .meta-grid {{ display: grid; gap: 8px; margin-bottom: 14px; }}
    .meta-row {{ display: grid; grid-template-columns: 120px 1fr; gap: 8px; font-size: 13px; }}
    .meta-row span:first-child {{ color: var(--muted); font-weight: 700; }}
    .editor {{ display: grid; gap: 12px; }}
    .editor textarea {{ min-height: 120px; padding: 10px; resize: vertical; }}
    .editor .checkbox-line {{ display: flex; align-items: center; gap: 8px; color: var(--ink); font-weight: 700; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }}
    .statusline {{ min-height: 22px; color: var(--accent-dark); font-size: 13px; font-weight: 700; }}
    .images {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .image-box h3 {{ margin: 0 0 8px; font-size: 16px; }}
    .image-frame {{
      min-height: 220px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: auto;
      padding: 8px;
    }}
    .image-frame img {{ display: block; width: 100%; height: auto; }}
    .missing {{ color: var(--bad); font-weight: 700; }}
    .debug-path {{ margin-top: 6px; color: var(--muted); font-size: 12px; word-break: break-all; }}
    .flag-list {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }}
    .flag {{ border: 1px solid var(--line); border-radius: 8px; padding: 3px 6px; font-size: 12px; color: var(--muted); }}
    .empty {{ padding: 28px; color: var(--muted); background: var(--surface); border: 1px solid var(--line); border-radius: 8px; }}
    input[type="file"] {{ max-width: 260px; }}
    @media (max-width: 980px) {{
      .layout, .images {{ grid-template-columns: 1fr; }}
      .meta-row {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<main>
  <div class="topbar">
    <label>Paper
      <select id="paperSelect"></select>
    </label>
    <label>Jump to question
      <select id="jumpSelect"></select>
    </label>
    <button id="prevButton" class="secondary" type="button">Previous</button>
    <button id="nextButton" type="button">Next</button>
    <button id="copyIdButton" class="secondary" type="button">Copy question id</button>
  </div>

  <div class="filters">
    <label><input id="onlyUnreviewed" type="checkbox"> only unreviewed</label>
    <label><input id="onlyUnusable" type="checkbox"> only unusable</label>
    <label><input id="onlyCropIssues" type="checkbox"> only crop issues</label>
    <label><input id="onlyWithImages" type="checkbox"> only with question images</label>
    <label><input id="missingMarkschemes" type="checkbox"> missing mark schemes</label>
  </div>

  <div id="stats" class="stats"></div>
  <div id="emptyState" class="empty" hidden>No records match the current filters.</div>

  <div id="reviewLayout" class="layout">
    <section class="panel">
      <h2 id="questionTitle">Question</h2>
      <div id="reviewState" class="pill">Unreviewed</div>
      <div id="metadata" class="meta-grid"></div>
      <div id="flags" class="flag-list"></div>
      <hr>
      <div class="editor">
        <label>Manual topic
          <select id="manualTopic"></select>
        </label>
        <label>Manual difficulty
          <select id="manualDifficulty">
            <option value="">not set</option>
            <option value="easy">easy</option>
            <option value="medium">medium</option>
            <option value="hard">hard</option>
          </select>
        </label>
        <label class="checkbox-line"><input id="usable" type="checkbox"> usable for students</label>
        <label>Crop status
          <select id="cropStatus">
            <option value="">not set</option>
            <option value="ok">ok</option>
            <option value="needs_fix">needs_fix</option>
            <option value="bad">bad</option>
          </select>
        </label>
        <label>Notes
          <textarea id="notes" placeholder="What should be fixed or checked?"></textarea>
        </label>
        <div class="actions">
          <button id="saveButton" type="button">Save</button>
          <button id="flagUnusableButton" class="danger" type="button">Flag unusable</button>
          <button id="exportButton" class="secondary" type="button">Export review JSON</button>
          <label class="secondary">Import review JSON
            <input id="importFile" type="file" accept="application/json,.json">
          </label>
        </div>
        <div id="saveStatus" class="statusline"></div>
      </div>
    </section>

    <section>
      <div class="images">
        <div class="image-box">
          <h3>Question image</h3>
          <div id="questionImageFrame" class="image-frame"></div>
        </div>
        <div class="image-box">
          <h3>Mark scheme image</h3>
          <div id="markschemeImageFrame" class="image-frame"></div>
        </div>
      </div>
    </section>
  </div>
</main>
<script>
window.MANUAL_REVIEW_RECORDS = {records_json};
window.TOPICS_BY_PAPER = {topics_json};
window.MANUAL_REVIEW_METADATA = {metadata_json};
</script>
<script>
(() => {{
  const STORAGE_KEY = 'examBankManualReview:v1';
  const records = Array.isArray(window.MANUAL_REVIEW_RECORDS) ? window.MANUAL_REVIEW_RECORDS : [];
  const topicsByPaper = window.TOPICS_BY_PAPER || {{}};
  const metadata = window.MANUAL_REVIEW_METADATA || {{}};
  let state = loadState();
  let filtered = [];
  let currentIndex = 0;
  let saveTimer = 0;

  const els = {{
    paperSelect: document.getElementById('paperSelect'),
    jumpSelect: document.getElementById('jumpSelect'),
    prevButton: document.getElementById('prevButton'),
    nextButton: document.getElementById('nextButton'),
    copyIdButton: document.getElementById('copyIdButton'),
    onlyUnreviewed: document.getElementById('onlyUnreviewed'),
    onlyUnusable: document.getElementById('onlyUnusable'),
    onlyCropIssues: document.getElementById('onlyCropIssues'),
    onlyWithImages: document.getElementById('onlyWithImages'),
    missingMarkschemes: document.getElementById('missingMarkschemes'),
    stats: document.getElementById('stats'),
    emptyState: document.getElementById('emptyState'),
    reviewLayout: document.getElementById('reviewLayout'),
    questionTitle: document.getElementById('questionTitle'),
    reviewState: document.getElementById('reviewState'),
    metadata: document.getElementById('metadata'),
    flags: document.getElementById('flags'),
    manualTopic: document.getElementById('manualTopic'),
    manualDifficulty: document.getElementById('manualDifficulty'),
    usable: document.getElementById('usable'),
    cropStatus: document.getElementById('cropStatus'),
    notes: document.getElementById('notes'),
    saveButton: document.getElementById('saveButton'),
    flagUnusableButton: document.getElementById('flagUnusableButton'),
    exportButton: document.getElementById('exportButton'),
    importFile: document.getElementById('importFile'),
    saveStatus: document.getElementById('saveStatus'),
    questionImageFrame: document.getElementById('questionImageFrame'),
    markschemeImageFrame: document.getElementById('markschemeImageFrame'),
  }};

  function loadState() {{
    try {{
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}');
      return {{
        reviews: parsed.reviews && typeof parsed.reviews === 'object' ? parsed.reviews : {{}},
        selectedPaper: parsed.selectedPaper || '',
        filters: parsed.filters && typeof parsed.filters === 'object' ? parsed.filters : {{}},
      }};
    }} catch (error) {{
      console.warn('Manual review localStorage was reset because it could not be parsed.', error);
      return {{ reviews: {{}}, selectedPaper: '', filters: {{}} }};
    }}
  }}

  function persistState() {{
    localStorage.setItem(STORAGE_KEY, JSON.stringify({{
      version: 1,
      updated_at: new Date().toISOString(),
      source: metadata.question_bank || '',
      selectedPaper: state.selectedPaper,
      filters: state.filters,
      reviews: state.reviews,
    }}));
  }}

  function reviewFor(record) {{
    return state.reviews[record.record_id] || {{}};
  }}

  function isReviewed(record) {{
    const review = reviewFor(record);
    return Boolean(review.reviewed_at || review.manual_topic || review.manual_difficulty || typeof review.usable === 'boolean' || review.crop_status || review.notes);
  }}

  function effectiveUsable(record) {{
    const review = reviewFor(record);
    if (typeof review.usable === 'boolean') return review.usable;
    if (typeof record.usable === 'boolean') return record.usable;
    return record.student_usable !== false;
  }}

  function effectiveCropStatus(record) {{
    return reviewFor(record).crop_status || record.crop_status || '';
  }}

  function hasCropIssue(record) {{
    const cropStatus = effectiveCropStatus(record);
    const flags = []
      .concat(record.review_flags || [])
      .concat(record.qa_warnings || []);
    return cropStatus === 'needs_fix' || cropStatus === 'bad' || flags.some(flag => String(flag).toLowerCase().includes('crop'));
  }}

  function populatePaperSelect() {{
    const paperMap = new Map();
    for (const record of records) {{
      if (!record.paper_key) continue;
      const label = `${{record.paper_title || record.paper_key}}${{record.paper_family ? ' (' + record.paper_family + ')' : ''}}`;
      paperMap.set(record.paper_key, label);
    }}
    const papers = Array.from(paperMap.keys()).sort((a, b) => paperMap.get(a).localeCompare(paperMap.get(b)));
    els.paperSelect.innerHTML = '';
    for (const paper of papers) {{
      const option = document.createElement('option');
      option.value = paper;
      option.textContent = paperMap.get(paper);
      els.paperSelect.append(option);
    }}
    if (!state.selectedPaper || !papers.includes(state.selectedPaper)) {{
      state.selectedPaper = papers[0] || '';
    }}
    els.paperSelect.value = state.selectedPaper;
  }}

  function syncFilterInputs() {{
    for (const key of ['onlyUnreviewed', 'onlyUnusable', 'onlyCropIssues', 'onlyWithImages', 'missingMarkschemes']) {{
      els[key].checked = Boolean(state.filters[key]);
    }}
  }}

  function buildFiltered() {{
    filtered = records.filter(record => {{
      if (state.selectedPaper && record.paper_key !== state.selectedPaper) return false;
      if (state.filters.onlyUnreviewed && isReviewed(record)) return false;
      if (state.filters.onlyUnusable && effectiveUsable(record)) return false;
      if (state.filters.onlyCropIssues && !hasCropIssue(record)) return false;
      if (state.filters.onlyWithImages && !record.question_image_exists) return false;
      if (state.filters.missingMarkschemes && record.markscheme_image_exists) return false;
      return true;
    }});
    if (currentIndex >= filtered.length) currentIndex = Math.max(0, filtered.length - 1);
  }}

  function renderStats() {{
    const paperRecords = records.filter(record => !state.selectedPaper || record.paper_key === state.selectedPaper);
    const total = paperRecords.length;
    const reviewed = paperRecords.filter(isReviewed).length;
    const usable = paperRecords.filter(effectiveUsable).length;
    const needsFix = paperRecords.filter(record => effectiveCropStatus(record) === 'needs_fix').length;
    const bad = paperRecords.filter(record => effectiveCropStatus(record) === 'bad').length;
    const current = filtered.length ? currentIndex + 1 : 0;
    els.stats.innerHTML = [
      `Reviewed ${{reviewed}} / ${{total}}`,
      `Unreviewed ${{Math.max(0, total - reviewed)}}`,
      `Usable ${{usable}}`,
      `Needs-fix ${{needsFix}}`,
      `Bad crop ${{bad}}`,
      `Showing ${{current}} / ${{filtered.length}}`,
    ].map(text => `<span class="pill">${{escapeHtml(text)}}</span>`).join('');
  }}

  function renderJumpSelect() {{
    els.jumpSelect.innerHTML = '';
    filtered.forEach((record, index) => {{
      const option = document.createElement('option');
      option.value = String(index);
      option.textContent = `${{record.question_label || record.question_number || 'question'}} - ${{reviewFor(record).manual_topic || record.manual_topic || record.auto_topic || 'no topic'}}`;
      els.jumpSelect.append(option);
    }});
    els.jumpSelect.value = String(currentIndex);
  }}

  function renderCurrent() {{
    buildFiltered();
    renderStats();
    renderJumpSelect();
    const hasRecord = filtered.length > 0;
    els.emptyState.hidden = hasRecord;
    els.reviewLayout.hidden = !hasRecord;
    els.prevButton.disabled = !hasRecord || currentIndex <= 0;
    els.nextButton.disabled = !hasRecord || currentIndex >= filtered.length - 1;
    els.jumpSelect.disabled = !hasRecord;
    if (!hasRecord) return;

    const record = filtered[currentIndex];
    const review = reviewFor(record);
    const reviewed = isReviewed(record);
    els.questionTitle.textContent = `${{record.paper_family || 'Paper'}} question ${{record.question_label || record.question_number || ''}}`;
    els.reviewState.textContent = reviewed ? 'Reviewed' : 'Unreviewed';
    els.reviewState.style.color = reviewed ? 'var(--accent-dark)' : 'var(--warn)';
    els.metadata.innerHTML = metadataRows(record, review);
    renderFlags(record);
    renderTopicOptions(record, review);
    els.manualDifficulty.value = review.manual_difficulty || record.manual_difficulty || '';
    els.usable.checked = typeof review.usable === 'boolean'
      ? review.usable
      : (typeof record.usable === 'boolean' ? record.usable : record.student_usable !== false);
    els.cropStatus.value = review.crop_status || record.crop_status || '';
    els.notes.value = review.notes || record.notes || '';
    renderImage(els.questionImageFrame, record.question_image, record.question_image_exists, record.question_image_source_path, record.question_image_resolved_path, 'Question image');
    renderImage(els.markschemeImageFrame, record.markscheme_image, record.markscheme_image_exists, record.markscheme_image_source_path, record.markscheme_image_resolved_path, 'Mark scheme image');
  }}

  function metadataRows(record, review) {{
    const rows = [
      ['Paper', record.paper_title || record.paper_name],
      ['Paper family', record.paper_family],
      ['Question', record.question_label || record.question_number],
      ['Marks', record.marks_if_available],
      ['Auto topic', record.auto_topic],
      ['Manual topic', review.manual_topic || record.manual_topic],
      ['Auto difficulty', record.auto_difficulty],
      ['Manual difficulty', review.manual_difficulty || record.manual_difficulty],
      ['QA', record.qa_status],
      ['Source pages', record.source_page_number],
      ['MS pages', record.markscheme_page_number],
      ['Source PDF', record.source_pdf],
      ['Record id', record.record_id],
    ];
    return rows
      .filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== '')
      .map(([label, value]) => `<div class="meta-row"><span>${{escapeHtml(label)}}</span><span>${{escapeHtml(String(value))}}</span></div>`)
      .join('');
  }}

  function renderFlags(record) {{
    const flags = []
      .concat(record.review_flags || [])
      .concat(record.qa_warnings || []);
    els.flags.innerHTML = flags.slice(0, 18).map(flag => `<span class="flag">${{escapeHtml(flag)}}</span>`).join('');
  }}

  function renderTopicOptions(record, review) {{
    const topics = topicsByPaper[record.paper_family] || [];
    const selected = review.manual_topic || record.manual_topic || '';
    els.manualTopic.innerHTML = '<option value="">not set</option>';
    for (const topic of topics) {{
      const option = document.createElement('option');
      option.value = topic;
      option.textContent = topic;
      els.manualTopic.append(option);
    }}
    if (selected && !topics.includes(selected)) {{
      const option = document.createElement('option');
      option.value = selected;
      option.textContent = `${{selected}} (custom)`;
      els.manualTopic.append(option);
    }}
    els.manualTopic.value = selected;
  }}

  function renderImage(container, src, exists, sourcePath, resolvedPath, label) {{
    container.innerHTML = '';
    if (!src) {{
      container.innerHTML = `<div class="missing">${{label}} unavailable</div><div class="debug-path">source: missing</div>`;
      return;
    }}
    const img = document.createElement('img');
    img.src = src;
    img.alt = label;
    img.onerror = () => {{
      console.warn('Manual review image failed to load', {{ label, src, sourcePath, resolvedPath, exists }});
      img.replaceWith(Object.assign(document.createElement('div'), {{ className: 'missing', textContent: `${{label}} failed to load` }}));
    }};
    container.append(img);
    const path = document.createElement('div');
    path.className = 'debug-path';
    path.textContent = `path: ${{src}}`;
    container.append(path);
    if (!exists) {{
      const missing = document.createElement('div');
      missing.className = 'debug-path missing';
      missing.textContent = `missing at generation time: ${{resolvedPath || sourcePath || src}}`;
      container.append(missing);
    }}
  }}

  function saveCurrent(showStatus = true, rerender = true) {{
    if (!filtered.length) return;
    const record = filtered[currentIndex];
    const review = {{
      record_id: record.record_id,
      manual_topic: els.manualTopic.value,
      manual_difficulty: els.manualDifficulty.value,
      usable: els.usable.checked,
      crop_status: els.cropStatus.value,
      notes: els.notes.value.trim(),
      reviewed_at: new Date().toISOString(),
    }};
    state.reviews[record.record_id] = review;
    persistState();
    if (showStatus) flashStatus('Saved');
    if (rerender) renderCurrent();
  }}

  function flashStatus(message) {{
    els.saveStatus.textContent = message;
    clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => els.saveStatus.textContent = '', 1500);
  }}

  function setFilter(key, value) {{
    state.filters[key] = value;
    currentIndex = 0;
    persistState();
    renderCurrent();
  }}

  function exportReviews() {{
    persistState();
    const payload = {{
      version: 1,
      exported_at: new Date().toISOString(),
      source: metadata.question_bank || '',
      review_count: Object.keys(state.reviews).length,
      reviews: state.reviews,
    }};
    const blob = new Blob([JSON.stringify(payload, null, 2) + '\\n'], {{ type: 'application/json' }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `manual_review_${{new Date().toISOString().slice(0, 10)}}.json`;
    document.body.append(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    flashStatus('Review JSON exported');
  }}

  async function importReviews(file) {{
    if (!file) return;
    try {{
      const data = JSON.parse(await file.text());
      const incoming = data.reviews || data;
      let count = 0;
      if (incoming && typeof incoming === 'object' && !Array.isArray(incoming)) {{
        for (const [id, review] of Object.entries(incoming)) {{
          if (review && typeof review === 'object') {{
            state.reviews[id] = {{ ...review, record_id: id }};
            count += 1;
          }}
        }}
      }} else if (Array.isArray(incoming)) {{
        for (const review of incoming) {{
          if (review && review.record_id) {{
            state.reviews[review.record_id] = review;
            count += 1;
          }}
        }}
      }}
      persistState();
      flashStatus(`Imported ${{count}} reviews`);
      renderCurrent();
    }} catch (error) {{
      console.error('Could not import manual review JSON.', error);
      flashStatus('Import failed');
    }} finally {{
      els.importFile.value = '';
    }}
  }}

  function escapeHtml(value) {{
    return String(value).replace(/[&<>"']/g, char => ({{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }}[char]));
  }}

  els.paperSelect.addEventListener('change', () => {{
    state.selectedPaper = els.paperSelect.value;
    currentIndex = 0;
    persistState();
    renderCurrent();
  }});
  els.jumpSelect.addEventListener('change', () => {{
    currentIndex = Number(els.jumpSelect.value) || 0;
    renderCurrent();
  }});
  els.prevButton.addEventListener('click', () => {{
    if (currentIndex > 0) currentIndex -= 1;
    renderCurrent();
  }});
  els.nextButton.addEventListener('click', () => {{
    if (currentIndex < filtered.length - 1) currentIndex += 1;
    renderCurrent();
  }});
  els.copyIdButton.addEventListener('click', async () => {{
    if (!filtered.length) return;
    await navigator.clipboard.writeText(filtered[currentIndex].record_id);
    flashStatus('Question id copied');
  }});
  for (const key of ['onlyUnreviewed', 'onlyUnusable', 'onlyCropIssues', 'onlyWithImages', 'missingMarkschemes']) {{
    els[key].addEventListener('change', () => setFilter(key, els[key].checked));
  }}
  for (const input of [els.manualTopic, els.manualDifficulty, els.usable, els.cropStatus, els.notes]) {{
    input.addEventListener('change', () => saveCurrent(false));
  }}
  els.notes.addEventListener('blur', () => saveCurrent(false));
  els.notes.addEventListener('input', () => saveCurrent(false, false));
  els.saveButton.addEventListener('click', () => saveCurrent(true));
  els.flagUnusableButton.addEventListener('click', () => {{
    els.usable.checked = false;
    els.cropStatus.value = els.cropStatus.value || 'bad';
    saveCurrent(true);
  }});
  els.exportButton.addEventListener('click', exportReviews);
  els.importFile.addEventListener('change', () => importReviews(els.importFile.files[0]));
  document.addEventListener('keydown', event => {{
    const tag = (event.target && event.target.tagName || '').toLowerCase();
    if (['input', 'textarea', 'select'].includes(tag)) return;
    if (event.key === 'ArrowRight' || event.key.toLowerCase() === 'n') {{
      els.nextButton.click();
    }} else if (event.key === 'ArrowLeft' || event.key.toLowerCase() === 'p') {{
      els.prevButton.click();
    }} else if (event.key.toLowerCase() === 's') {{
      event.preventDefault();
      saveCurrent(true);
    }}
  }});

  populatePaperSelect();
  syncFilterInputs();
  buildFiltered();
  renderCurrent();
}})();
</script>
</body>
</html>
"""


def _safe_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return payload.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
