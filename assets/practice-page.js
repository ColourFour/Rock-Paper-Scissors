const family = window.EXAM_FAMILY;
const familyTitle = window.EXAM_TITLE || "Practice";

const state = {
  allQuestions: [],
  enrichments: {},
  imageAvailability: null,
  pool: [],
  index: 0,
  current: null,
  solutionVisible: false,
};

const elements = {
  title: document.querySelector("#paper-family-title"),
  paperSelect: document.querySelector("#paper-select"),
  topicSelect: document.querySelector("#topic-select"),
  difficultySelect: document.querySelector("#difficulty-select"),
  marksSelect: document.querySelector("#marks-select"),
  previousQuestion: document.querySelector("#previous-question"),
  randomQuestion: document.querySelector("#random-question"),
  nextQuestion: document.querySelector("#next-question"),
  checkSolution: document.querySelector("#check-solution"),
  status: document.querySelector("#status"),
  card: document.querySelector("#question-card"),
  questionTitle: document.querySelector("#question-title"),
  questionImage: document.querySelector("#question-image"),
  solution: document.querySelector("#solution"),
  solutionImage: document.querySelector("#solution-image"),
  currentPaper: document.querySelector("#current-paper"),
  currentQuestion: document.querySelector("#current-question"),
  currentTopic: document.querySelector("#current-topic"),
  currentMarks: document.querySelector("#current-marks"),
  currentDifficulty: document.querySelector("#current-difficulty"),
  warningBadge: document.querySelector("#warning-badge"),
  deepseek: document.querySelector("#deepseek-metadata"),
};

const difficultyLabels = {
  easy: "Easy",
  average: "Average",
  difficult: "Difficult",
  unknown: "Unknown",
};

const difficultyOrder = ["easy", "average", "difficult", "unknown"];
const queryFilters = new URLSearchParams(window.location.search);
const initialFilters = {
  paper: queryFilters.get("paper") || "all",
  topic: queryFilters.get("topic") || "all",
  difficulty: queryFilters.get("difficulty") || "all",
  marks: queryFilters.get("marks") || "all",
};

function imageUrl(path) {
  return `../data/images/${path}`;
}

async function loadJson(path, optional = false) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    if (optional) {
      return null;
    }
    throw new Error(`Could not load ${path} (${response.status})`);
  }
  return response.json();
}

function normalizeQuestion(record) {
  return {
    id: record.question_id,
    paper: record.paper,
    paperFamily: record.paper_family,
    questionNumber: String(record.question_number),
    topic: record.topic || "unknown",
    marks: record.question_solution_marks,
    questionImage: imageUrl(record.question_image_path),
    markSchemeImage: imageUrl(record.mark_scheme_image_path),
    validationStatus: record.validation_status,
    notes: record.notes || {},
  };
}

function hasImages(record) {
  if (!record.question_image_path || !record.mark_scheme_image_path) {
    return false;
  }
  if (!state.imageAvailability) {
    return true;
  }
  return state.imageAvailability.available?.[record.question_id] === true;
}

function questionsForFamily() {
  return state.allQuestions.filter((question) => question.paperFamily === family);
}

function questionsForPaperSelection() {
  const selectedPaper = elements.paperSelect.value;
  const questions = questionsForFamily();
  if (selectedPaper === "all") {
    return questions;
  }
  return questions.filter((question) => question.paper === selectedPaper);
}

function questionsForPaperAndTopicSelection() {
  const selectedTopic = elements.topicSelect.value;
  const questions = questionsForPaperSelection();
  if (selectedTopic === "all") {
    return questions;
  }
  return questions.filter((question) => normalizedTopic(question.topic) === selectedTopic);
}

function questionsForPaperTopicAndDifficultySelection() {
  const selectedDifficulty = elements.difficultySelect.value;
  const questions = questionsForPaperAndTopicSelection();
  if (selectedDifficulty === "all") {
    return questions;
  }
  return questions.filter((question) => difficultyFor(question) === selectedDifficulty);
}

function questionsForSelection() {
  const selectedMarks = elements.marksSelect.value;
  const questions = questionsForPaperTopicAndDifficultySelection();
  if (selectedMarks === "all") {
    return questions;
  }
  return questions.filter((question) => marksValue(question) === selectedMarks);
}

function populatePaperSelect() {
  const papers = [...new Set(questionsForFamily().map((question) => question.paper))].sort(comparePaper);
  elements.paperSelect.innerHTML = '<option value="all">All papers</option>';
  papers.forEach((paper) => {
    const option = document.createElement("option");
    option.value = paper;
    option.textContent = paper;
    elements.paperSelect.append(option);
  });
}

function populateTopicSelect() {
  const previousValue = elements.topicSelect.value;
  const topics = [...new Set(questionsForPaperSelection().map((question) => normalizedTopic(question.topic)))].sort();
  elements.topicSelect.innerHTML = '<option value="all">All topics</option>';
  topics.forEach((topic) => {
    const option = document.createElement("option");
    option.value = topic;
    option.textContent = formatTopic(topic);
    elements.topicSelect.append(option);
  });
  elements.topicSelect.value = previousValue === "all" || topics.includes(previousValue) ? previousValue : "all";
}

function populateDifficultySelect() {
  const previousValue = elements.difficultySelect.value;
  const available = new Set(questionsForPaperAndTopicSelection().map(difficultyFor));
  elements.difficultySelect.innerHTML = '<option value="all">All difficulties</option>';
  difficultyOrder.forEach((difficulty) => {
    const option = document.createElement("option");
    option.value = difficulty;
    option.textContent = difficultyLabels[difficulty];
    elements.difficultySelect.append(option);
  });
  elements.difficultySelect.value = previousValue === "all" || available.has(previousValue) ? previousValue : "all";
}

function populateMarksSelect() {
  const previousValue = elements.marksSelect.value;
  const markValues = [...new Set(questionsForPaperTopicAndDifficultySelection().map(marksValue))];
  const numericMarks = markValues
    .filter((value) => value !== "unknown")
    .sort((a, b) => Number(a) - Number(b));
  const hasUnknown = markValues.includes("unknown");
  const available = new Set(numericMarks);

  elements.marksSelect.innerHTML = '<option value="all">All marks</option>';
  numericMarks.forEach((marks) => {
    const option = document.createElement("option");
    option.value = marks;
    option.textContent = `${marks} marks`;
    elements.marksSelect.append(option);
  });
  if (hasUnknown) {
    const option = document.createElement("option");
    option.value = "unknown";
    option.textContent = "Unknown";
    elements.marksSelect.append(option);
    available.add("unknown");
  }

  elements.marksSelect.value = previousValue === "all" || available.has(previousValue) ? previousValue : "all";
}

function refreshDependentFilters({ resetTopic = false, resetDifficulty = false, resetMarks = false } = {}) {
  if (resetTopic) {
    elements.topicSelect.value = "all";
  }
  populateTopicSelect();
  if (resetDifficulty) {
    elements.difficultySelect.value = "all";
  }
  populateDifficultySelect();
  if (resetMarks) {
    elements.marksSelect.value = "all";
  }
  populateMarksSelect();
}

function resetPool({ randomize = true } = {}) {
  state.pool = questionsForSelection();
  if (randomize) {
    shuffle(state.pool);
  } else {
    state.pool.sort(compareQuestion);
  }
  state.index = 0;
  updateUrlParams();
  showCurrentQuestion();
}

function showCurrentQuestion() {
  state.solutionVisible = false;
  elements.solution.classList.remove("visible");
  elements.solutionImage.removeAttribute("src");
  elements.checkSolution.textContent = "Check solution";

  if (!state.pool.length) {
    state.current = null;
    renderEmpty("No questions match these filters.");
    return;
  }

  state.current = state.pool[state.index % state.pool.length];
  renderQuestion();
}

function previousQuestion() {
  if (!state.pool.length) {
    return;
  }
  state.index = (state.index - 1 + state.pool.length) % state.pool.length;
  showCurrentQuestion();
}

function nextQuestion() {
  if (!state.pool.length) {
    return;
  }
  state.index = (state.index + 1) % state.pool.length;
  showCurrentQuestion();
}

function randomQuestion() {
  resetPool({ randomize: true });
}

function renderQuestion() {
  const question = state.current;
  const enrichment = state.enrichments[question.id] || {};
  const difficulty = difficultyFor(question);
  setNavigationDisabled(false);
  elements.status.hidden = true;
  elements.card.hidden = false;
  elements.title.textContent = familyTitle;
  elements.questionTitle.textContent = `${question.paper} - Question ${question.questionNumber}`;
  elements.questionImage.src = question.questionImage;
  elements.questionImage.alt = `${question.paper} question ${question.questionNumber}`;
  elements.currentPaper.textContent = `Paper: ${question.paper}`;
  elements.currentQuestion.textContent = `Question: ${question.questionNumber}`;
  elements.currentTopic.textContent = `Topic: ${formatTopic(question.topic)}`;
  elements.currentMarks.textContent = question.marks ? `Marks: ${question.marks}` : "Marks: not detected";
  elements.currentDifficulty.textContent = `Difficulty: ${difficultyLabels[difficulty]}`;
  renderWarning(question, enrichment);
  renderDeepSeek(enrichment);
}

function renderWarning(question, enrichment) {
  const reasons = warningReasons(question, enrichment);
  if (!reasons.length) {
    elements.warningBadge.hidden = true;
    elements.warningBadge.textContent = "";
    return;
  }
  elements.warningBadge.hidden = false;
  elements.warningBadge.textContent = `Review warning: ${reasons.join(", ")}`;
}

function warningReasons(question, enrichment) {
  const reasons = [];
  if (question.validationStatus && question.validationStatus !== "pass") {
    reasons.push(`validation ${question.validationStatus}`);
  }
  if (question.notes.mapping_status && question.notes.mapping_status !== "pass") {
    reasons.push(`mapping ${question.notes.mapping_status}`);
  }
  if (question.notes.visual_curation_status === "fail") {
    reasons.push("visual curation fail");
  }
  if (question.notes.text_only_status === "fail") {
    reasons.push("text review fail");
  }
  if (enrichment.final_review_required === true) {
    reasons.push("DeepSeek review required");
  }
  return reasons;
}

function renderDeepSeek(enrichment) {
  const rows = [];
  addDeepSeekRow(rows, "DeepSeek topic", enrichment.deepseek_topic);
  addDeepSeekRow(rows, "Subtopic", enrichment.deepseek_subtopic);
  addDeepSeekRow(rows, "Difficulty", enrichment.deepseek_difficulty);
  addDeepSeekRow(rows, "Confidence", enrichment.deepseek_confidence_normalized);
  addDeepSeekRow(rows, "Reconciliation", enrichment.topic_reconciliation_status);
  if (enrichment.final_review_required === true) {
    addDeepSeekRow(rows, "Review reasons", (enrichment.final_review_reasons || []).join(", "));
  }
  elements.deepseek.innerHTML = rows.join("");
}

function addDeepSeekRow(rows, label, value) {
  if (value === undefined || value === null || value === "") {
    return;
  }
  rows.push(`<span><strong>${escapeHtml(label)}:</strong> ${escapeHtml(String(value))}</span>`);
}

function renderEmpty(message) {
  setNavigationDisabled(true);
  elements.card.hidden = true;
  elements.status.hidden = false;
  elements.status.className = "status error";
  elements.status.textContent = message;
}

function toggleSolution() {
  if (!state.current) {
    return;
  }
  state.solutionVisible = !state.solutionVisible;
  if (state.solutionVisible) {
    elements.solutionImage.src = state.current.markSchemeImage;
    elements.solutionImage.alt = `${state.current.paper} mark scheme for question ${state.current.questionNumber}`;
  } else {
    elements.solutionImage.removeAttribute("src");
  }
  elements.solution.classList.toggle("visible", state.solutionVisible);
  elements.checkSolution.textContent = state.solutionVisible ? "Hide solution" : "Check solution";
}

function setNavigationDisabled(disabled) {
  elements.previousQuestion.disabled = disabled;
  elements.randomQuestion.disabled = disabled;
  elements.nextQuestion.disabled = disabled;
}

function difficultyFor(question) {
  const enrichment = state.enrichments[question.id] || {};
  return normalizeDifficulty(enrichment.deepseek_difficulty_normalized || enrichment.deepseek_difficulty || "unknown");
}

function normalizeDifficulty(value) {
  const normalized = String(value || "unknown").trim().toLowerCase().replace(/\s+/g, "_");
  if (normalized === "easy") {
    return "easy";
  }
  if (["average", "medium", "moderate"].includes(normalized)) {
    return "average";
  }
  if (["difficult", "hard"].includes(normalized)) {
    return "difficult";
  }
  return "unknown";
}

function marksValue(question) {
  if (question.marks === undefined || question.marks === null || question.marks === "") {
    return "unknown";
  }
  return String(question.marks);
}

function applyInitialFilters() {
  setSelectValue(elements.paperSelect, initialFilters.paper);
  refreshDependentFilters();
  setSelectValue(elements.topicSelect, initialFilters.topic);
  refreshDependentFilters();
  setSelectValue(elements.difficultySelect, normalizeInitialDifficulty(initialFilters.difficulty));
  populateMarksSelect();
  setSelectValue(elements.marksSelect, initialFilters.marks);
}

function normalizeInitialDifficulty(value) {
  if (value === "all") {
    return "all";
  }
  return normalizeDifficulty(value);
}

function setSelectValue(select, value) {
  if ([...select.options].some((option) => option.value === value)) {
    select.value = value;
  }
}

function updateUrlParams() {
  const params = new URLSearchParams();
  setQueryParam(params, "paper", elements.paperSelect.value);
  setQueryParam(params, "topic", elements.topicSelect.value);
  setQueryParam(params, "difficulty", elements.difficultySelect.value);
  setQueryParam(params, "marks", elements.marksSelect.value);
  const query = params.toString();
  const nextUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
  window.history.replaceState(null, "", nextUrl);
}

function setQueryParam(params, key, value) {
  if (value && value !== "all") {
    params.set(key, value);
  }
}

function formatTopic(topic) {
  return String(topic || "unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function normalizedTopic(topic) {
  return String(topic || "unknown");
}

function compareQuestion(a, b) {
  return comparePaper(a.paper, b.paper) || compareQuestionNumber(a.questionNumber, b.questionNumber);
}

function comparePaper(a, b) {
  const parsedA = parsePaper(a);
  const parsedB = parsePaper(b);
  return parsedA.component - parsedB.component || parsedA.year - parsedB.year || parsedA.season - parsedB.season || a.localeCompare(b);
}

function parsePaper(paper) {
  const match = String(paper).match(/^(\d+)(spring|summer|autumn)(\d+)$/);
  if (!match) {
    return { component: 999, season: 999, year: 999 };
  }
  const seasonOrder = { spring: 1, summer: 2, autumn: 3 };
  return {
    component: Number(match[1]),
    season: seasonOrder[match[2]] || 999,
    year: Number(match[3]),
  };
}

function compareQuestionNumber(a, b) {
  const numericA = Number(a);
  const numericB = Number(b);
  if (Number.isFinite(numericA) && Number.isFinite(numericB)) {
    return numericA - numericB;
  }
  return String(a).localeCompare(String(b));
}

function shuffle(items) {
  for (let index = items.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [items[index], items[swapIndex]] = [items[swapIndex], items[index]];
  }
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

elements.paperSelect.addEventListener("change", () => {
  refreshDependentFilters({ resetTopic: true, resetDifficulty: true, resetMarks: true });
  resetPool({ randomize: false });
});
elements.topicSelect.addEventListener("change", () => {
  refreshDependentFilters({ resetDifficulty: true, resetMarks: true });
  resetPool({ randomize: false });
});
elements.difficultySelect.addEventListener("change", () => {
  populateMarksSelect();
  resetPool({ randomize: false });
});
elements.marksSelect.addEventListener("change", () => resetPool({ randomize: false }));
elements.previousQuestion.addEventListener("click", previousQuestion);
elements.randomQuestion.addEventListener("click", randomQuestion);
elements.nextQuestion.addEventListener("click", nextQuestion);
elements.checkSolution.addEventListener("click", toggleSolution);

Promise.all([
  loadJson("../data/json/question_bank.json"),
  loadJson("../data/json/question_bank.deepseek.full.json", true),
  loadJson("../data/json/image_availability.json", true),
])
  .then(([bank, deepseek, imageAvailability]) => {
    state.enrichments = deepseek?.enrichments || {};
    state.imageAvailability = imageAvailability;
    state.allQuestions = (bank.questions || [])
      .filter((record) => record.paper_family === family && hasImages(record))
      .map(normalizeQuestion)
      .sort(compareQuestion);
    elements.title.textContent = familyTitle;
    populatePaperSelect();
    applyInitialFilters();
    resetPool({ randomize: false });
  })
  .catch((error) => {
    const suffix = window.location.protocol === "file:" ? " Run this through GitHub Pages or a local web server, not by opening the file directly." : "";
    renderEmpty(`${error.message}.${suffix}`);
  });
