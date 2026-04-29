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
  const familyQuestions = questionsForFamily();
  const papers = [...new Set(familyQuestions.map((question) => question.paper))].sort(comparePaper);
  elements.paperSelect.innerHTML = "";
  appendCountedOption(elements.paperSelect, "all", "All papers", familyQuestions.length);
  papers.forEach((paper) => {
    const count = familyQuestions.filter((question) => question.paper === paper).length;
    appendCountedOption(elements.paperSelect, paper, paper, count);
  });
  syncSelectCountLabels(elements.paperSelect);
}

function populateTopicSelect() {
  const previousValue = elements.topicSelect.value;
  const questions = questionsForPaperSelection();
  const topicCounts = countBy(questions, topicKeyFor);
  const topics = [...topicCounts.keys()].sort(compareTopicKeys);
  elements.topicSelect.innerHTML = "";
  appendCountedOption(elements.topicSelect, "all", "All topics", questions.length);
  topics.forEach((topic) => {
    appendCountedOption(elements.topicSelect, topic, formatTopic(topic), topicCounts.get(topic));
  });
  elements.topicSelect.value = previousValue === "all" || topics.includes(previousValue) ? previousValue : "all";
  syncSelectCountLabels(elements.topicSelect);
}

function populateDifficultySelect() {
  const previousValue = elements.difficultySelect.value;
  const questions = questionsForPaperAndTopicSelection();
  const difficultyCounts = countBy(questions, difficultyFor);
  const available = new Set(difficultyCounts.keys());
  elements.difficultySelect.innerHTML = "";
  appendCountedOption(elements.difficultySelect, "all", "All difficulties", questions.length);
  difficultyOrder.forEach((difficulty) => {
    appendCountedOption(elements.difficultySelect, difficulty, difficultyLabels[difficulty], difficultyCounts.get(difficulty) || 0);
  });
  elements.difficultySelect.value = previousValue === "all" || available.has(previousValue) ? previousValue : "all";
  syncSelectCountLabels(elements.difficultySelect);
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

  elements.marksSelect.innerHTML = "";
  appendCountedOption(elements.marksSelect, "all", "All marks", questions.length);
  numericMarks.forEach((marks) => {
    appendCountedOption(elements.marksSelect, marks, formatMarksGroup(marks), markCounts.get(marks));
  });
  if (hasTwelvePlus) {
    appendCountedOption(elements.marksSelect, "12plus", "12+ marks", markCounts.get("12plus"));
    available.add("12plus");
  }
  if (hasMiscellaneous) {
    appendCountedOption(elements.marksSelect, "miscellaneous", "Miscellaneous", markCounts.get("miscellaneous"));
    available.add("miscellaneous");
  }

  elements.marksSelect.value = previousValue === "all" || available.has(previousValue) ? previousValue : "all";
  syncSelectCountLabels(elements.marksSelect);
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
  return broadTopicKey(enrichment.deepseek_topic_normalized || enrichment.deepseek_topic || question.topic || "miscellaneous");
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

function appendCountedOption(select, value, label, count) {
  const option = document.createElement("option");
  option.value = value;
  option.dataset.label = label;
  option.dataset.count = String(count);
  option.textContent = `${label} (${count})`;
  select.append(option);
}

function syncSelectCountLabels(select) {
  [...select.options].forEach((option) => {
    const label = option.dataset.label || option.textContent;
    const count = option.dataset.count;
    option.textContent = option.selected || count === undefined ? label : `${label} (${count})`;
  });
}

function syncAllSelectCountLabels() {
  [elements.paperSelect, elements.topicSelect, elements.difficultySelect, elements.marksSelect].forEach(syncSelectCountLabels);
}

function applyInitialFilters() {
  setSelectValue(elements.paperSelect, initialFilters.paper);
  refreshDependentFilters();
  setSelectValue(elements.topicSelect, broadTopicKey(initialFilters.topic));
  refreshDependentFilters();
  setSelectValue(elements.difficultySelect, normalizeInitialDifficulty(initialFilters.difficulty));
  populateMarksSelect();
  setSelectValue(elements.marksSelect, normalizeInitialMarks(initialFilters.marks));
  syncAllSelectCountLabels();
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
  const labels = {
    binomial_expansion: "Binomial expansion",
    binomial_distribution: "Binomial distribution",
    connected_particles: "Connected particles",
    coordinate_geometry: "Coordinate geometry",
    complex_numbers: "Complex numbers",
    differential_equations: "Differential equations",
    discrete_random_variables: "Discrete random variables",
    forces_newtons_laws: "Forces and Newton's laws",
    hypothesis_testing: "Hypothesis testing",
    logarithms_exponentials: "Logarithms and exponentials",
    normal_distribution: "Normal distribution",
    numerical_methods: "Numerical methods",
    permutations_combinations: "Permutations and combinations",
    series_sequences: "Series and sequences",
    work_energy_power: "Work, energy and power",
  };
  if (labels[topic]) {
    return labels[topic];
  }
  return String(topic || "miscellaneous")
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function broadTopicKey(value) {
  const text = cleanTopicText(value);
  if (!text || text === "unknown" || text === "miscellaneous") {
    return "miscellaneous";
  }

  if (text.startsWith("dynamics")) {
    return "dynamics";
  }
  if (text.startsWith("kinematics") || text === "motion graphs") {
    return "kinematics";
  }
  if (["momentum", "momentum impulse", "impulse"].includes(text)) {
    return "momentum";
  }
  if (["work energy power", "work energy and power", "power and resistance", "energy"].includes(text)) {
    return "work_energy_power";
  }
  if (text.includes("connected particles")) {
    return "connected_particles";
  }
  if ([
    "equilibrium particle",
    "equilibrium of forces",
    "equilibrium of coplanar forces",
    "equilibrium coplanar forces",
    "forces in equilibrium",
  ].includes(text)) {
    return "equilibrium";
  }
  if (["forces", "forces and newtons laws", "newtons laws of motion"].includes(text)) {
    return "forces_newtons_laws";
  }
  if (["friction", "friction rough plane", "rough plane"].includes(text)) {
    return "friction";
  }

  if (["binomial expansion", "binomial theorem"].includes(text)) {
    return "binomial_expansion";
  }
  if (["coordinate geometry", "circles", "equation of circle"].includes(text)) {
    return "coordinate_geometry";
  }
  if (["quadratics", "quadratic equations", "discriminant"].includes(text)) {
    return "quadratics";
  }
  if (["functions", "transformations", "graph transformations", "inverse functions", "composite functions"].includes(text)) {
    return "functions";
  }
  if (["differentiation", "derivatives", "applications of differentiation"].includes(text)) {
    return "differentiation";
  }
  if (["integration", "definite integration", "indefinite integration", "area under curve"].includes(text)) {
    return "integration";
  }
  if (["trigonometry", "trigonometric equations", "trig identities"].includes(text)) {
    return "trigonometry";
  }
  if (["series and sequences", "sequences and series", "arithmetic progression", "geometric progression"].includes(text)) {
    return "series_sequences";
  }
  if (["logarithms and exponentials", "exponentials and logarithms", "logarithms", "exponentials"].includes(text)) {
    return "logarithms_exponentials";
  }
  if (["vectors", "vector geometry"].includes(text)) {
    return "vectors";
  }
  if (["complex numbers", "argand diagram"].includes(text)) {
    return "complex_numbers";
  }
  if (["numerical methods", "iteration"].includes(text)) {
    return "numerical_methods";
  }
  if (text === "differential equations") {
    return "differential_equations";
  }

  if (["discrete random variables", "random variables", "probability distributions"].includes(text)) {
    return "discrete_random_variables";
  }
  if (["probability", "conditional probability", "independent events"].includes(text)) {
    return "probability";
  }
  if (["statistics", "descriptive statistics", "representation of data", "data representation"].includes(text)) {
    return "statistics";
  }
  if (text === "binomial distribution") {
    return "binomial_distribution";
  }
  if (text === "normal distribution") {
    return "normal_distribution";
  }
  if (text === "hypothesis testing") {
    return "hypothesis_testing";
  }
  if (["permutations and combinations", "combinations", "permutations"].includes(text)) {
    return "permutations_combinations";
  }

  return normalizeKey(text);
}

function cleanTopicText(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/&/g, " and ")
    .replace(/[_-]+/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeKey(value) {
  const normalized = cleanTopicText(value).replace(/\s+/g, "_");
  if (!normalized || normalized === "unknown") {
    return "miscellaneous";
  }
  return normalized;
}

function compareTopicKeys(a, b) {
  if (a === "miscellaneous" && b !== "miscellaneous") {
    return 1;
  }
  if (b === "miscellaneous" && a !== "miscellaneous") {
    return -1;
  }
  return formatTopic(a).localeCompare(formatTopic(b));
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
  syncAllSelectCountLabels();
  refreshDependentFilters({ resetTopic: true, resetDifficulty: true, resetMarks: true });
  resetPool({ randomize: false });
});
elements.topicSelect.addEventListener("change", () => {
  syncAllSelectCountLabels();
  refreshDependentFilters({ resetDifficulty: true, resetMarks: true });
  resetPool({ randomize: false });
});
elements.difficultySelect.addEventListener("change", () => {
  syncAllSelectCountLabels();
  populateMarksSelect();
  resetPool({ randomize: false });
});
elements.marksSelect.addEventListener("change", () => {
  syncAllSelectCountLabels();
  resetPool({ randomize: false });
});
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
