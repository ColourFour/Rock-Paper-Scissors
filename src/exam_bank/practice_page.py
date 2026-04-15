from __future__ import annotations

from dataclasses import dataclass
import html
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PracticePageResult:
    html_path: Path
    usable_records: int
    skipped_records: int


def build_practice_page(question_bank_path: str | Path, output_dir: str | Path) -> PracticePageResult:
    question_bank_path = Path(question_bank_path)
    output_dir = Path(output_dir)
    records = _load_question_bank(question_bank_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    practice_records: list[dict[str, Any]] = []
    skipped = 0
    for record in records:
        practice_record = _practice_record(record, output_dir)
        if practice_record is None:
            skipped += 1
        else:
            practice_records.append(practice_record)

    html_path = output_dir / "index.html"
    html_path.write_text(_html_document(practice_records), encoding="utf-8")
    return PracticePageResult(
        html_path=html_path,
        usable_records=len(practice_records),
        skipped_records=skipped,
    )


def _load_question_bank(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Question bank JSON must be a list of records.")
    return [item for item in data if isinstance(item, dict)]


def _practice_record(record: dict[str, Any], output_dir: Path) -> dict[str, Any] | None:
    paper_family = _text(record.get("paper_family") or record.get("question_level_paper_family"))
    topic = _text(record.get("topic") or record.get("question_level_topic"))
    question_number = _text(record.get("question_number"))
    question_image = _text(record.get("question_image") or record.get("screenshot_path"))
    markscheme_image = _text(record.get("markscheme_image"))

    if not paper_family or not topic or not question_number or not question_image or not markscheme_image:
        return None

    question_src = _browser_path(question_image, output_dir)
    markscheme_src = _browser_path(markscheme_image, output_dir)
    if not question_src or not markscheme_src:
        return None

    return {
        "paper_family": paper_family,
        "topic": topic,
        "question_number": question_number,
        "marks_if_available": record.get("marks_if_available") or record.get("marks") or "",
        "question_image": question_src,
        "markscheme_image": markscheme_src,
    }


def _browser_path(value: str, output_dir: Path) -> str:
    if value.startswith(("http://", "https://", "data:")):
        return value

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return ""

    try:
        relative = path.resolve().relative_to(output_dir.resolve())
    except ValueError:
        relative = Path(_relative_path(path.resolve(), output_dir.resolve()))
    return relative.as_posix()


def _relative_path(path: Path, start: Path) -> str:
    import os

    return os.path.relpath(path, start=start)


def _html_document(records: list[dict[str, Any]]) -> str:
    data_json = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    data_json = data_json.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
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

    .answer-controls {{
      margin: 16px 0;
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

      <div class="answer-controls">
        <button id="markschemeButton" type="button">Show mark scheme</button>
      </div>

      <section id="markschemeArea" class="markscheme" hidden>
        <h2>Mark scheme</h2>
        <img id="markschemeImage" class="exam-image" alt="Mark scheme screenshot">
      </section>
    </section>
  </main>

  <script>
    window.QUESTION_BANK = {data_json};
  </script>
  <script>
    const records = Array.isArray(window.QUESTION_BANK) ? window.QUESTION_BANK : [];
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
      markschemeArea.hidden = true;
      markschemeButton.textContent = "Show mark scheme";
      questionArea.hidden = false;
      setStatus("");
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
