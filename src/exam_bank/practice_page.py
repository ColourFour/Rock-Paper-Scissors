from __future__ import annotations

from dataclasses import dataclass
import html
import json
import shutil
from pathlib import Path
from typing import Any

from .config import PracticePageConfig


@dataclass(frozen=True)
class PracticePageResult:
    html_path: Path
    usable_records: int
    skipped_records: int
    copied_assets: int = 0
    missing_assets: int = 0


def build_practice_page(
    question_bank_path: str | Path,
    output_dir: str | Path,
    config: PracticePageConfig | None = None,
    *,
    copy_assets: bool = False,
    asset_dir_name: str = "assets",
) -> PracticePageResult:
    question_bank_path = Path(question_bank_path)
    output_dir = Path(output_dir)
    config = config or PracticePageConfig()
    records = _load_question_bank(question_bank_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    asset_resolver = _AssetResolver(output_dir, copy_assets=copy_assets, asset_dir_name=asset_dir_name)

    practice_records: list[dict[str, Any]] = []
    skipped = 0
    for record in records:
        practice_record = _practice_record(record, asset_resolver)
        if practice_record is None:
            skipped += 1
        else:
            practice_records.append(practice_record)

    html_path = output_dir / "index.html"
    html_path.write_text(_html_document(practice_records, _bug_report_payload(config)), encoding="utf-8")
    return PracticePageResult(
        html_path=html_path,
        usable_records=len(practice_records),
        skipped_records=skipped,
        copied_assets=asset_resolver.copied_count,
        missing_assets=asset_resolver.missing_count,
    )


def _load_question_bank(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Question bank JSON must be a list of records.")
    return [item for item in data if isinstance(item, dict)]


def _practice_record(record: dict[str, Any], asset_resolver: "_AssetResolver") -> dict[str, Any] | None:
    paper_family = _text(record.get("paper_family") or record.get("question_level_paper_family"))
    topic = _text(record.get("topic") or record.get("question_level_topic"))
    question_number = _text(record.get("question_number"))
    question_image = _text(record.get("question_image") or record.get("screenshot_path"))
    markscheme_image = _text(record.get("markscheme_image"))

    if not paper_family or not topic or not question_number or not question_image or not markscheme_image:
        return None

    question_asset = asset_resolver.browser_asset(question_image)
    markscheme_asset = asset_resolver.browser_asset(markscheme_image)
    if not question_asset["src"] or not markscheme_asset["src"]:
        return None

    return {
        "paper_family": paper_family,
        "topic": topic,
        "question_number": question_number,
        "question_id": _text(record.get("question_id") or f"{record.get('paper_name') or paper_family}:Q{question_number}"),
        "question_label": _text(record.get("full_question_label") or record.get("question_label") or question_number),
        "paper_name": _text(record.get("paper_name")),
        "source_pdf": _text(record.get("source_pdf")),
        "session": _text(record.get("session")),
        "year": _text(record.get("year")),
        "component": _text(record.get("component") or record.get("source_paper_code")),
        "source_page_number": _page_numbers_text(record.get("page_numbers") or record.get("question_pages")),
        "markscheme_page_number": _page_numbers_text(record.get("markscheme_pages")),
        "qa_status": _qa_status(record),
        "qa_warnings": _qa_warnings(record),
        "pipeline_topic": topic,
        "marks_if_available": record.get("marks_if_available") or record.get("marks") or "",
        "question_image": question_asset["src"],
        "question_image_source_path": question_image,
        "question_image_resolved_path": question_asset["resolved_path"],
        "question_image_exists": question_asset["exists"],
        "markscheme_image": markscheme_asset["src"],
        "markscheme_image_source_path": markscheme_image,
        "markscheme_image_resolved_path": markscheme_asset["resolved_path"],
        "markscheme_image_exists": markscheme_asset["exists"],
    }


def _bug_report_payload(config: PracticePageConfig) -> dict[str, Any]:
    bug_report = config.bug_report
    return {
        "enabled": bool(bug_report.enabled),
        "form_url": str(bug_report.form_url or ""),
        "open_in_new_tab": bool(bug_report.open_in_new_tab),
        "enable_copy_button": bool(bug_report.enable_copy_button),
        "form_field_names": dict(bug_report.form_field_names),
    }


class _AssetResolver:
    def __init__(self, output_dir: Path, *, copy_assets: bool, asset_dir_name: str) -> None:
        self.output_dir = output_dir
        self.copy_assets = copy_assets
        self.asset_dir_name = asset_dir_name.strip().strip("/") or "assets"
        self._copied: set[Path] = set()
        self._missing: set[Path] = set()

    @property
    def copied_count(self) -> int:
        return len(self._copied)

    @property
    def missing_count(self) -> int:
        return len(self._missing)

    def browser_asset(self, value: str) -> dict[str, Any]:
        if value.startswith(("http://", "https://", "data:")):
            return {"src": value, "resolved_path": value, "exists": True}

        path = Path(value).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path

        resolved = path.resolve()
        exists = resolved.exists()
        if self.copy_assets:
            return self._copied_asset(resolved, exists=exists)

        try:
            relative = resolved.relative_to(self.output_dir.resolve())
        except ValueError:
            relative = Path(_relative_path(resolved, self.output_dir.resolve()))
        return {
            "src": relative.as_posix(),
            "resolved_path": str(resolved),
            "exists": exists,
        }

    def _copied_asset(self, source: Path, *, exists: bool) -> dict[str, Any]:
        relative_source = _source_asset_relative(source)
        browser_path = Path(self.asset_dir_name) / relative_source
        destination = self.output_dir / browser_path

        if exists:
            if source not in self._copied:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if source != destination.resolve():
                    shutil.copy2(source, destination)
                self._copied.add(source)
        else:
            self._missing.add(source)

        return {
            "src": browser_path.as_posix(),
            "resolved_path": browser_path.as_posix(),
            "exists": exists,
        }


def _source_asset_relative(path: Path) -> Path:
    try:
        return path.relative_to(Path.cwd().resolve())
    except ValueError:
        return Path(path.name)


def _relative_path(path: Path, start: Path) -> str:
    import os

    return os.path.relpath(path, start=start)


def _html_document(records: list[dict[str, Any]], bug_report_config: dict[str, Any]) -> str:
    data_json = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    data_json = data_json.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    bug_report_json = json.dumps(bug_report_config, ensure_ascii=False, separators=(",", ":"))
    bug_report_json = bug_report_json.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Question Practice</title>
  <style>
    :root {{
      color-scheme: light;
      --background: #f6f8f4;
      --ink: #18201a;
      --muted: #59635b;
      --line: #c9d2ca;
      --surface: #ffffff;
      --accent: #24735a;
      --accent-dark: #1b5845;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background: var(--background);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }}

    main {{
      width: min(1120px, calc(100% - 32px));
      margin: 22px auto 48px;
    }}

    .controls {{
      display: flex;
      flex-wrap: wrap;
      align-items: end;
      gap: 12px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--line);
    }}

    label {{
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }}

    select,
    button {{
      min-height: 40px;
      border-radius: 8px;
      font: inherit;
    }}

    select {{
      min-width: min(360px, 86vw);
      padding: 8px 10px;
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--ink);
    }}

    button {{
      border: 1px solid var(--accent);
      background: var(--accent);
      color: #fff;
      cursor: pointer;
      font-weight: 700;
      padding: 8px 14px;
    }}

    button:hover {{
      background: var(--accent-dark);
    }}

    button:disabled {{
      cursor: not-allowed;
      opacity: 0.55;
    }}

    .status {{
      min-height: 24px;
      margin: 14px 0;
      color: var(--muted);
    }}

    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin: 14px 0 12px;
      color: var(--muted);
      font-weight: 700;
    }}

    .meta span {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      padding: 5px 8px;
    }}

    .exam-image {{
      display: block;
      max-width: 100%;
      height: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
    }}

    .asset-debug {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}

    .answer-controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      margin: 16px 0;
    }}

    .secondary-button {{
      border-color: var(--line);
      background: var(--surface);
      color: var(--ink);
    }}

    .secondary-button:hover {{
      border-color: var(--accent);
      background: #eef5f1;
    }}

    .report-status {{
      min-height: 18px;
      color: var(--muted);
      font-size: 13px;
    }}

    .markscheme {{
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
    }}

    .markscheme h2 {{
      margin: 0 0 12px;
      font-size: 18px;
      letter-spacing: 0;
    }}

    [hidden] {{
      display: none !important;
    }}

    @media (max-width: 680px) {{
      main {{
        width: min(100% - 20px, 1120px);
        margin-top: 12px;
      }}

      .controls {{
        align-items: stretch;
      }}

      .controls > *,
      select,
      button {{
        width: 100%;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="controls" aria-label="Practice controls">
      <label>Paper
        <select id="paperSelect"></select>
      </label>
      <label>Topic
        <select id="topicSelect"></select>
      </label>
      <button id="questionButton" type="button">Give me a question</button>
    </section>

    <p id="status" class="status" role="status"></p>

    <section id="questionArea" hidden>
      <div class="meta">
        <span id="paperMeta"></span>
        <span id="topicMeta"></span>
        <span id="questionMeta"></span>
        <span id="marksMeta"></span>
      </div>

      <img id="questionImage" class="exam-image" alt="Question screenshot">
      <p id="questionImageDebug" class="asset-debug"></p>

      <div class="answer-controls">
        <button id="markschemeButton" type="button">Show mark scheme</button>
        <button id="reportButton" class="secondary-button" type="button" hidden>Report a problem</button>
        <button id="copyReportButton" class="secondary-button" type="button" hidden>Copy bug report</button>
        <span id="bugReportStatus" class="report-status" role="status"></span>
      </div>

      <section id="markschemeArea" class="markscheme" hidden>
        <h2>Mark scheme</h2>
        <img id="markschemeImage" class="exam-image" alt="Mark scheme screenshot">
        <p id="markschemeImageDebug" class="asset-debug"></p>
      </section>
    </section>
  </main>

  <script>
    window.QUESTION_BANK = {data_json};
    window.BUG_REPORT_CONFIG = {bug_report_json};
  </script>
  <script>
    const records = Array.isArray(window.QUESTION_BANK) ? window.QUESTION_BANK : [];
    const bugReportConfig = window.BUG_REPORT_CONFIG || {{}};
    const state = {{ current: null }};

    const paperSelect = document.querySelector("#paperSelect");
    const topicSelect = document.querySelector("#topicSelect");
    const questionButton = document.querySelector("#questionButton");
    const markschemeButton = document.querySelector("#markschemeButton");
    const statusLine = document.querySelector("#status");
    const questionArea = document.querySelector("#questionArea");
    const markschemeArea = document.querySelector("#markschemeArea");
    const paperMeta = document.querySelector("#paperMeta");
    const topicMeta = document.querySelector("#topicMeta");
    const questionMeta = document.querySelector("#questionMeta");
    const marksMeta = document.querySelector("#marksMeta");
    const questionImage = document.querySelector("#questionImage");
    const markschemeImage = document.querySelector("#markschemeImage");
    const questionImageDebug = document.querySelector("#questionImageDebug");
    const markschemeImageDebug = document.querySelector("#markschemeImageDebug");
    const reportButton = document.querySelector("#reportButton");
    const copyReportButton = document.querySelector("#copyReportButton");
    const bugReportStatus = document.querySelector("#bugReportStatus");

    // Static pages cannot store submissions without a backend. The practice page
    // therefore opens an external form and offers a clipboard fallback instead.

    function topicLabel(topic) {{
      return String(topic || "").replaceAll("_", " ");
    }}

    function setStatus(message) {{
      statusLine.textContent = message;
    }}

    function setupPaperOptions() {{
      const papers = [...new Set(records.map((record) => record.paper_family).filter(Boolean))]
        .sort((a, b) => a.localeCompare(b, undefined, {{ numeric: true }}));

      paperSelect.innerHTML = "";
      for (const paper of papers) {{
        const count = records.filter((record) => record.paper_family === paper).length;
        const option = document.createElement("option");
        option.value = paper;
        option.textContent = `${{paper}} (${{count}})`;
        paperSelect.appendChild(option);
      }}

      if (!papers.length) {{
        paperSelect.innerHTML = '<option value="">No papers available</option>';
        topicSelect.innerHTML = '<option value="">No topics available</option>';
        questionButton.disabled = true;
        setStatus("No usable records were embedded in this page.");
        return;
      }}

      updateTopicOptions();
      setStatus(`${{records.length}} questions ready.`);
    }}

    function updateTopicOptions() {{
      const paper = paperSelect.value;
      const paperRecords = records.filter((record) => record.paper_family === paper);
      const topics = [...new Set(paperRecords.map((record) => record.topic).filter(Boolean))]
        .sort((a, b) => topicLabel(a).localeCompare(topicLabel(b)));

      topicSelect.innerHTML = "";
      for (const topic of topics) {{
        const count = paperRecords.filter((record) => record.topic === topic).length;
        const option = document.createElement("option");
        option.value = topic;
        option.textContent = `${{topicLabel(topic)}} (${{count}})`;
        topicSelect.appendChild(option);
      }}

      if (!topics.length) {{
        topicSelect.innerHTML = '<option value="">No topics available</option>';
        questionButton.disabled = true;
      }} else {{
        questionButton.disabled = false;
      }}
    }}

    function showRandomQuestion() {{
      const paper = paperSelect.value;
      const topic = topicSelect.value;
      const choices = records.filter((record) => record.paper_family === paper && record.topic === topic);
      if (!choices.length) {{
        setStatus("No questions match that paper and topic.");
        questionArea.hidden = true;
        return;
      }}

      const record = choices[Math.floor(Math.random() * choices.length)];
      state.current = record;

      paperMeta.textContent = record.paper_family;
      topicMeta.textContent = topicLabel(record.topic);
      questionMeta.textContent = `Question ${{record.question_number}}`;
      marksMeta.textContent = record.marks_if_available ? `${{record.marks_if_available}} marks` : "Marks not shown";
      questionImage.src = record.question_image;
      markschemeImage.src = record.markscheme_image;
      updateAssetDebug("question", record, questionImageDebug);
      updateAssetDebug("markscheme", record, markschemeImageDebug);
      markschemeArea.hidden = true;
      markschemeButton.textContent = "Show mark scheme";
      updateBugReportControls(record);
      questionArea.hidden = false;
      setStatus("");
    }}

    function updateBugReportControls(record) {{
      bugReportStatus.textContent = "";
      const enabled = bugReportConfig.enabled !== false;
      reportButton.hidden = !(enabled && bugReportConfig.form_url);
      copyReportButton.hidden = !(enabled && bugReportConfig.enable_copy_button !== false);
      reportButton.disabled = !record;
      copyReportButton.disabled = !record;
    }}

    function valueOrMissing(value) {{
      if (value === undefined || value === null || value === "") return "missing";
      if (Array.isArray(value) && !value.length) return "missing";
      return String(Array.isArray(value) ? value.join(", ") : value);
    }}

    function buildBugReportText(record) {{
      const lines = [
        "Issue type:",
        "Description:",
        "Expected result:",
        "Actual result:",
        "",
        `Paper: ${{valueOrMissing(record.paper_family)}}`,
        `Topic: ${{valueOrMissing(record.topic)}}`,
        `Question number: ${{valueOrMissing(record.question_number)}}`,
        `Marks: ${{valueOrMissing(record.marks_if_available)}}`,
        `Source PDF: ${{valueOrMissing(record.source_pdf)}}`,
        `Question image path: ${{valueOrMissing(record.question_image_source_path)}}`,
        `Mark scheme image path: ${{valueOrMissing(record.markscheme_image_source_path)}}`,
        `Question label: ${{valueOrMissing(record.question_label)}}`,
        `Question id: ${{valueOrMissing(record.question_id)}}`,
        `Session/year: ${{valueOrMissing([record.session, record.year].filter(Boolean).join(" "))}}`,
        `Component: ${{valueOrMissing(record.component)}}`,
        `Source page number: ${{valueOrMissing(record.source_page_number)}}`,
        `Mark scheme page number: ${{valueOrMissing(record.markscheme_page_number)}}`,
        `QA status / warnings: ${{valueOrMissing([record.qa_status, record.qa_warnings].filter(Boolean).join(" | "))}}`,
        `Topic assigned by pipeline: ${{valueOrMissing(record.pipeline_topic)}}`,
      ];
      return lines.join("\\n");
    }}

    function formValueMap(record) {{
      return {{
        paper: valueOrMissing(record.paper_family),
        topic: valueOrMissing(record.topic),
        question_number: valueOrMissing(record.question_number),
        marks: valueOrMissing(record.marks_if_available),
        source_pdf: valueOrMissing(record.source_pdf),
        question_image: valueOrMissing(record.question_image_source_path),
        markscheme_image: valueOrMissing(record.markscheme_image_source_path),
        report_text: buildBugReportText(record),
      }};
    }}

    function bugReportFormUrl(record) {{
      const rawUrl = bugReportConfig.form_url || "";
      if (!rawUrl) return "";
      const values = formValueMap(record);
      const fieldNames = bugReportConfig.form_field_names || {{}};
      try {{
        const url = new URL(rawUrl, window.location.href);
        for (const [key, value] of Object.entries(values)) {{
          const fieldName = fieldNames[key] || key;
          if (fieldName) url.searchParams.set(fieldName, value);
        }}
        return url.toString();
      }} catch (error) {{
        const params = new URLSearchParams();
        for (const [key, value] of Object.entries(values)) {{
          const fieldName = fieldNames[key] || key;
          if (fieldName) params.set(fieldName, value);
        }}
        return `${{rawUrl}}${{rawUrl.includes("?") ? "&" : "?"}}${{params.toString()}}`;
      }}
    }}

    async function copyTextToClipboard(text) {{
      if (navigator.clipboard && window.isSecureContext) {{
        await navigator.clipboard.writeText(text);
        return;
      }}
      const textArea = document.createElement("textarea");
      textArea.value = text;
      textArea.setAttribute("readonly", "");
      textArea.style.position = "fixed";
      textArea.style.left = "-9999px";
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      textArea.remove();
    }}

    function updateAssetDebug(kind, record, target) {{
      const src = record[`${{kind}}_image`] || "";
      const sourcePath = record[`${{kind}}_image_source_path`] || src;
      const resolvedPath = record[`${{kind}}_image_resolved_path`] || "";
      const exists = record[`${{kind}}_image_exists`];
      target.textContent = `image src: ${{src}} | source: ${{sourcePath}}${{resolvedPath ? ` | resolved: ${{resolvedPath}}` : ""}}`;
      if (exists === false) {{
        console.warn("Practice image missing at generation time", {{
          record_id: `${{record.paper_family}}:${{record.topic}}:${{record.question_number}}`,
          kind,
          expected_image_path: sourcePath,
          resolved_path: resolvedPath,
          exists_at_generation: exists,
        }});
      }}
    }}

    function reportImageError(kind, record, image) {{
      console.warn("Practice image failed to load", {{
        record_id: record ? `${{record.paper_family}}:${{record.topic}}:${{record.question_number}}` : "",
        kind,
        image_src: image.getAttribute("src"),
        expected_image_path: record ? record[`${{kind}}_image_source_path`] : "",
        resolved_path: record ? record[`${{kind}}_image_resolved_path`] : "",
        exists_at_generation: record ? record[`${{kind}}_image_exists`] : undefined,
      }});
    }}

    paperSelect.addEventListener("change", () => {{
      updateTopicOptions();
      questionArea.hidden = true;
      setStatus("Choose a topic, then ask for a question.");
    }});

    topicSelect.addEventListener("change", () => {{
      questionArea.hidden = true;
      setStatus("Ready.");
    }});

    questionButton.addEventListener("click", showRandomQuestion);

    questionImage.addEventListener("error", () => reportImageError("question", state.current, questionImage));
    markschemeImage.addEventListener("error", () => reportImageError("markscheme", state.current, markschemeImage));

    reportButton.addEventListener("click", () => {{
      if (!state.current) return;
      const url = bugReportFormUrl(state.current);
      if (!url) {{
        bugReportStatus.textContent = "No report form configured.";
        return;
      }}
      if (bugReportConfig.open_in_new_tab === false) {{
        window.location.href = url;
      }} else {{
        window.open(url, "_blank", "noopener,noreferrer");
      }}
    }});

    copyReportButton.addEventListener("click", async () => {{
      if (!state.current) return;
      try {{
        await copyTextToClipboard(buildBugReportText(state.current));
        bugReportStatus.textContent = "Bug report copied.";
      }} catch (error) {{
        bugReportStatus.textContent = "Copy failed. Select and copy the details from the console.";
        console.warn("Bug report copy failed", {{ error, bug_report: buildBugReportText(state.current) }});
      }}
    }});

    markschemeButton.addEventListener("click", () => {{
      if (!state.current) return;
      markschemeArea.hidden = false;
      markschemeButton.textContent = "Mark scheme shown";
    }});

    setupPaperOptions();
  </script>
</body>
</html>
"""


def _text(value: Any) -> str:
    if value is None:
        return ""
    return html.unescape(str(value)).strip()


def _page_numbers_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item not in {None, ""})
    if value in {None, ""}:
        return ""
    return str(value)


def _qa_status(record: dict[str, Any]) -> str:
    value = record.get("qa_status")
    if value:
        return _text(value)
    qa = record.get("qa")
    if isinstance(qa, dict):
        return _text(qa.get("status"))
    return ""


def _qa_warnings(record: dict[str, Any]) -> str:
    values = record.get("qa_flags")
    if not values:
        qa = record.get("qa")
        if isinstance(qa, dict):
            values = qa.get("flags")
    if isinstance(values, list):
        return ", ".join(str(value) for value in values if value)
    return _text(values)
