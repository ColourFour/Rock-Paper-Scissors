const family = window.EXAM_FAMILY;
const familyTitle = window.EXAM_TITLE || "Practice";
const compactFamilyTitle = window.EXAM_COMPACT_TITLE || familyTitle;

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
  footerQuote: document.querySelector("#footer-quote"),
};

const difficultyLabels = {
  easy: "Easy",
  average: "Average",
  difficult: "Difficult",
  miscellaneous: "Miscellaneous",
};

const difficultyOrder = ["easy", "average", "difficult", "miscellaneous"];
const quotes = [
  "Pressure means you are in the game.",
  "Hard questions make strong mathematicians.",
  "Earn the calm by doing the reps.",
  "The exam is not bigger than your preparation.",
  "One clean step at a time.",
  "Steady practice turns nerves into focus.",
  "Show your method. Trust your training.",
  "Make the hard thing familiar.",
];
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
  return questions.filter((question) => topicKeyFor(question) === selectedTopic);
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
  return questions.filter((question) => marksGroupFor(question) === selectedMarks);
}

function populatePaperSelect() {
  const papers = [...new Set(questionsForFamily().map((question) => question.paper))].sort(comparePaper);
  elements.paperSelect.innerHTML = `<option value="all">All papers (${questionsForFamily().length})</option>`;
  papers.forEach((paper) => {
    const count = questionsForFamily().filter((question) => question.paper === paper).length;
    const option = document.createElement("option");
    option.value = paper;
    option.textContent = `${paper} (${count})`;
    elements.paperSelect.append(option);
  });
}

function populateTopicSelect() {
  const previousValue = elements.topicSelect.value;
  const questions = questionsForPaperSelection();
  const topicCounts = countBy(questions, topicKeyFor);
  const topics = [...topicCounts.keys()].sort((a, b) => formatTopic(a).localeCompare(formatTopic(b)));
  elements.topicSelect.innerHTML = `<option value="all">All topics (${questions.length})</option>`;
  topics.forEach((topic) => {
    const option = document.createElement("option");
    option.value = topic;
    option.textContent = `${formatTopic(topic)} (${topicCounts.get(topic)})`;
    elements.topicSelect.append(option);
  });
  elements.topicSelect.value = previousValue === "all" || topics.includes(previousValue) ? previousValue : "all";
}

function populateDifficultySelect() {
  const previousValue = elements.difficultySelect.value;
  const questions = questionsForPaperAndTopicSelection();
  const difficultyCounts = countBy(questions, difficultyFor);
  const available = new Set(difficultyCounts.keys());
  elements.difficultySelect.innerHTML = `<option value="all">All difficulties (${questions.length})</option>`;
  difficultyOrder.forEach((difficulty) => {
    const option = document.createElement("option");
    option.value = difficulty;
    option.textContent = `${difficultyLabels[difficulty]} (${difficultyCounts.get(difficulty) || 0})`;
    elements.difficultySelect.append(option);
  });
  elements.difficultySelect.value = previousValue === "all" || available.has(previousValue) ? previousValue : "all";
}

function populateMarksSelect() {
  const previousValue = elements.marksSelect.value;
  const questions = questionsForPaperTopicAndDifficultySelection();
  const markCounts = countBy(questions, marksGroupFor);
  const markValues = [...markCounts.keys()];
  const numericMarks = markValues
    .filter((value) => !["12plus", "miscellaneous"].includes(value))
    .sort((a, b) => Number(a) - Number(b));
  const hasTwelvePlus = markValues.includes("12plus");
  const hasMiscellaneous = markValues.includes("miscellaneous");
  const available = new Set(numericMarks);

  elements.marksSelect.innerHTML = `<option value="all">All marks (${questions.length})</option>`;
  numericMarks.forEach((marks) => {
    const option = document.createElement("option");
    option.value = marks;
    option.textContent = `${formatMarksGroup(marks)} (${markCounts.get(marks)})`;
    elements.marksSelect.append(option);
  });
  if (hasTwelvePlus) {
    const option = document.createElement("option");
    option.value = "12plus";
    option.textContent = `12+ marks (${markCounts.get("12plus")})`;
    elements.marksSelect.append(option);
    available.add("12plus");
  }
  if (hasMiscellaneous) {
    const option = document.createElement("option");
    option.value = "miscellaneous";
    option.textContent = `Miscellaneous (${markCounts.get("miscellaneous")})`;
    elements.marksSelect.append(option);
    available.add("miscellaneous");
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
  const difficulty = difficultyFor(question);
  setNavigationDisabled(false);
  elements.status.hidden = true;
  elements.card.hidden = false;
  elements.title.textContent = compactFamilyTitle;
  elements.questionTitle.textContent = `${question.paper} - Question ${question.questionNumber}`;
  elements.questionImage.src = question.questionImage;
  elements.questionImage.alt = `${question.paper} question ${question.questionNumber}`;
  elements.currentPaper.textContent = `Paper: ${question.paper}`;
  elements.currentQuestion.textContent = `Question: ${question.questionNumber}`;
  elements.currentTopic.textContent = `Topic: ${formatTopic(topicKeyFor(question))}`;
  elements.currentMarks.textContent = `Marks: ${formatMarksGroup(marksGroupFor(question))}`;
  elements.currentDifficulty.textContent = `Difficulty: ${difficultyLabels[difficulty]}`;
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
  return normalizeDifficulty(enrichment.deepseek_difficulty_normalized || enrichment.deepseek_difficulty || "miscellaneous");
}

function normalizeDifficulty(value) {
  const normalized = normalizeKey(value);
  if (normalized === "easy") {
    return "easy";
  }
  if (["average", "medium", "moderate"].includes(normalized)) {
    return "average";
  }
  if (["difficult", "hard"].includes(normalized)) {
    return "difficult";
  }
  return "miscellaneous";
}

function topicKeyFor(question) {
  const enrichment = state.enrichments[question.id] || {};
  return normalizeKey(enrichment.deepseek_topic_normalized || enrichment.deepseek_topic || question.topic || "miscellaneous");
}

function marksGroupFor(question) {
  const marks = Number(question.marks);
  if (!Number.isFinite(marks)) {
    return "miscellaneous";
  }
  if (marks >= 12) {
    return "12plus";
  }
  return String(marks);
}

function formatMarksGroup(group) {
  if (group === "12plus") {
    return "12+ marks";
  }
  if (group === "miscellaneous") {
    return "Miscellaneous";
  }
  return Number(group) === 1 ? "1 mark" : `${group} marks`;
}

function countBy(items, keyFor) {
  const counts = new Map();
  items.forEach((item) => {
    const key = keyFor(item);
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  return counts;
}

function applyInitialFilters() {
  setSelectValue(elements.paperSelect, initialFilters.paper);
  refreshDependentFilters();
  setSelectValue(elements.topicSelect, normalizeKey(initialFilters.topic));
  refreshDependentFilters();
  setSelectValue(elements.difficultySelect, normalizeInitialDifficulty(initialFilters.difficulty));
  populateMarksSelect();
  setSelectValue(elements.marksSelect, normalizeInitialMarks(initialFilters.marks));
}

function normalizeInitialDifficulty(value) {
  if (value === "all") {
    return "all";
  }
  return normalizeDifficulty(value);
}

function normalizeInitialMarks(value) {
  if (value === "all") {
    return "all";
  }
  const marks = Number(value);
  if (Number.isFinite(marks)) {
    return marks >= 12 ? "12plus" : String(marks);
  }
  const normalized = normalizeKey(value);
  return ["12plus", "miscellaneous"].includes(normalized) ? normalized : "miscellaneous";
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
  return String(topic || "miscellaneous")
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function normalizeKey(value) {
  const normalized = String(value || "").trim().toLowerCase().replace(/\s+/g, "_");
  if (!normalized || normalized === "unknown") {
    return "miscellaneous";
  }
  return normalized;
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
    elements.title.textContent = compactFamilyTitle;
    populatePaperSelect();
    applyInitialFilters();
    setFooterQuote();
    resetPool({ randomize: false });
  })
  .catch((error) => {
    const suffix = window.location.protocol === "file:" ? " Run this through GitHub Pages or a local web server, not by opening the file directly." : "";
    renderEmpty(`${error.message}.${suffix}`);
  });

function setFooterQuote() {
  if (!elements.footerQuote) {
    return;
  }
  elements.footerQuote.textContent = quotes[Math.floor(Math.random() * quotes.length)];
}
