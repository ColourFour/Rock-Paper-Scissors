const family = window.EXAM_FAMILY;
const familyTitle = window.EXAM_TITLE || "Practice";
const compactFamilyTitle = window.EXAM_COMPACT_TITLE || familyTitle;

const state = {
  allQuestions: [],
  topicRoutes: {},
  imageAvailability: null,
  pool: [],
  index: 0,
  current: null,
  solutionVisible: false,
  seenQuestionIds: [],
};

const elements = {
  title: document.querySelector("#paper-family-title"),
  paperSelect: document.querySelector("#paper-select"),
  topicSelect: document.querySelector("#topic-select"),
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
  seenCount: document.querySelector("#seen-count"),
  exportSeen: document.querySelector("#export-seen"),
  clearSeen: document.querySelector("#clear-seen"),
  footerQuote: document.querySelector("#footer-quote"),
};

const topicTaxonomies = {
  p1: [
    { key: "quadratics", label: "Quadratics" },
    { key: "functions", label: "Functions" },
    { key: "coordinate_geometry", label: "Coordinate geometry" },
    { key: "circular_measure", label: "Circular measure" },
    { key: "trigonometry", label: "Trigonometry" },
    { key: "series", label: "Series" },
    { key: "differentiation", label: "Differentiation" },
    { key: "integration", label: "Integration" },
  ],
  p3: [
    { key: "algebra", label: "Algebra" },
    { key: "logarithmic_exponential_functions", label: "Logarithmic and exponential functions" },
    { key: "trigonometry", label: "Trigonometry" },
    { key: "differentiation", label: "Differentiation" },
    { key: "integration", label: "Integration" },
    { key: "numerical_solution_equations", label: "Numerical solution of equations" },
    { key: "vectors", label: "Vectors" },
    { key: "differential_equations", label: "Differential equations" },
    { key: "complex_numbers", label: "Complex numbers" },
  ],
  p4: [
    { key: "forces_equilibrium", label: "Forces and equilibrium" },
    { key: "kinematics_motion_straight_line", label: "Kinematics of motion in a straight line" },
    { key: "momentum", label: "Momentum" },
    { key: "newtons_laws_motion", label: "Newton's laws of motion" },
    { key: "energy_work_power", label: "Energy, work and power" },
  ],
  p5: [
    { key: "representation_data", label: "Representation of data" },
    { key: "permutations_combinations", label: "Permutations and combinations" },
    { key: "probability", label: "Probability" },
    { key: "discrete_random_variables", label: "Discrete random variables" },
    { key: "normal_distribution", label: "The normal distribution" },
  ],
};

const topicAliases = {
  p1: {
    "9709_p1_topic_quadratics": "quadratics",
    "9709_p1_topic_functions": "functions",
    "9709_p1_topic_coordinate_geometry": "coordinate_geometry",
    "9709_p1_topic_circular_measure": "circular_measure",
    "9709_p1_topic_trigonometry": "trigonometry",
    "9709_p1_topic_series": "series",
    "9709_p1_topic_differentiation": "differentiation",
    "9709_p1_topic_integration": "integration",
    algebra: "quadratics",
    binomial_expansion: "series",
    circular_measure: "circular_measure",
    coordinate_geometry: "coordinate_geometry",
    differentiation: "differentiation",
    differentiation_integration: "differentiation",
    functions: "functions",
    integration: "integration",
    quadratics: "quadratics",
    series: "series",
    series_and_sequences: "series",
    series_sequences: "series",
    trigonometry: "trigonometry",
  },
  p3: {
    "9709_p3_topic_algebra": "algebra",
    "9709_p3_topic_logarithmic_and_exponential_functions": "logarithmic_exponential_functions",
    "9709_p3_topic_trigonometry": "trigonometry",
    "9709_p3_topic_differentiation": "differentiation",
    "9709_p3_topic_integration": "integration",
    "9709_p3_topic_numerical_solution_of_equations": "numerical_solution_equations",
    "9709_p3_topic_vectors": "vectors",
    "9709_p3_topic_differential_equations": "differential_equations",
    "9709_p3_topic_complex_numbers": "complex_numbers",
    algebra: "algebra",
    binomial_expansion: "algebra",
    complex_numbers: "complex_numbers",
    differential_equations: "differential_equations",
    differentiation: "differentiation",
    functions: "algebra",
    integration: "integration",
    logarithmic_and_exponential_functions: "logarithmic_exponential_functions",
    logarithmic_exponential_functions: "logarithmic_exponential_functions",
    logarithms_and_exponentials: "logarithmic_exponential_functions",
    logarithms_exponentials: "logarithmic_exponential_functions",
    modulus: "algebra",
    modulus_functions: "algebra",
    numerical_methods: "numerical_solution_equations",
    numerical_solution_equations: "numerical_solution_equations",
    numerical_solution_of_equations: "numerical_solution_equations",
    parametric_equations: "differentiation",
    partial_fractions: "algebra",
    polynomials: "algebra",
    trigonometry: "trigonometry",
    vectors: "vectors",
  },
  p4: {
    "9709_m1_topic_forces_and_equilibrium": "forces_equilibrium",
    "9709_m1_topic_kinematics_of_motion_in_a_straight_line": "kinematics_motion_straight_line",
    "9709_m1_topic_momentum": "momentum",
    "9709_m1_topic_newtons_laws_of_motion": "newtons_laws_motion",
    "9709_m1_topic_energy_work_and_power": "energy_work_power",
    connected_particles: "newtons_laws_motion",
    energy_work_power: "energy_work_power",
    equilibrium_coplanar_forces: "forces_equilibrium",
    equilibrium_particle: "forces_equilibrium",
    forces_and_equilibrium: "forces_equilibrium",
    forces_equilibrium: "forces_equilibrium",
    forces_newtons_laws: "newtons_laws_motion",
    forces_newtons_second_law: "newtons_laws_motion",
    friction: "forces_equilibrium",
    friction_rough_plane: "forces_equilibrium",
    kinematics: "kinematics_motion_straight_line",
    kinematics_constant_acceleration: "kinematics_motion_straight_line",
    kinematics_graphs: "kinematics_motion_straight_line",
    kinematics_motion_straight_line: "kinematics_motion_straight_line",
    kinematics_variable_functions: "kinematics_motion_straight_line",
    momentum: "momentum",
    momentum_impulse: "momentum",
    newtons_laws_motion: "newtons_laws_motion",
    newtons_laws_of_motion: "newtons_laws_motion",
    power_and_resistance: "energy_work_power",
    rough_plane_energy: "energy_work_power",
    work_energy_power: "energy_work_power",
  },
  p5: {
    "9709_s1_topic_representation_of_data": "representation_data",
    "9709_s1_topic_permutations_and_combinations": "permutations_combinations",
    "9709_s1_topic_probability": "probability",
    "9709_s1_topic_discrete_random_variables": "discrete_random_variables",
    "9709_s1_topic_the_normal_distribution": "normal_distribution",
    binomial_distribution: "discrete_random_variables",
    data_representation: "representation_data",
    discrete_random_variables: "discrete_random_variables",
    geometric_distribution: "discrete_random_variables",
    measures_of_central_tendency_and_dispersion: "representation_data",
    normal_distribution: "normal_distribution",
    permutations_and_combinations: "permutations_combinations",
    permutations_combinations: "permutations_combinations",
    probability: "probability",
    probability_distributions: "discrete_random_variables",
    representation_data: "representation_data",
    representation_of_data: "representation_data",
    statistics: "representation_data",
    the_normal_distribution: "normal_distribution",
  },
};

const topicLabels = Object.fromEntries(
  Object.values(topicTaxonomies)
    .flat()
    .map((topic) => [topic.key, topic.label]),
);

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
  marks: queryFilters.get("marks") || "all",
};
const dataRoot = window.PRACTICE_DATA_ROOT || "../data/step-3";
const imageAvailabilityPath = window.PRACTICE_IMAGE_AVAILABILITY_PATH || "";

function imageUrl(path) {
  return `${dataRoot}/${path}`;
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

async function loadFirstJson(paths, optional = false) {
  const errors = [];
  for (const path of paths) {
    try {
      return await loadJson(path);
    } catch (error) {
      errors.push(error.message);
    }
  }
  if (optional) {
    return null;
  }
  throw new Error(errors[errors.length - 1] || `Could not load ${paths[0]}`);
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
  if (state.imageAvailability.missing?.[record.question_id]) {
    return false;
  }
  if (!state.imageAvailability.available) {
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

function questionsForSelection() {
  const selectedMarks = elements.marksSelect.value;
  const questions = questionsForPaperAndTopicSelection();
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
  const topics = topicTaxonomyFor(family);
  elements.topicSelect.innerHTML = "";
  appendCountedOption(elements.topicSelect, "all", "All topics", questions.length);
  topics.forEach((topic) => {
    appendCountedOption(elements.topicSelect, topic.key, topic.label, topicCounts.get(topic.key) || 0);
  });
  elements.topicSelect.value = previousValue === "all" || topics.some((topic) => topic.key === previousValue) ? previousValue : "all";
  syncSelectCountLabels(elements.topicSelect);
}

function populateMarksSelect() {
  const previousValue = elements.marksSelect.value;
  const questions = questionsForPaperAndTopicSelection();
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

function refreshDependentFilters({ resetTopic = false, resetMarks = false } = {}) {
  if (resetTopic) {
    elements.topicSelect.value = "all";
  }
  populateTopicSelect();
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
  markQuestionSeen(question);
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

function seenStorageKey() {
  return `caie-math-review:seen:${family}:${localDateStamp()}`;
}

function localDateStamp(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function loadSeenQuestions() {
  state.seenQuestionIds = readSeenQuestionIds().filter((id) => {
    return state.allQuestions.some((question) => question.id === id);
  });
  updateSeenControls();
}

function readSeenQuestionIds() {
  try {
    const stored = window.localStorage.getItem(seenStorageKey());
    const parsed = JSON.parse(stored || "[]");
    return Array.isArray(parsed) ? parsed.filter((id) => typeof id === "string") : [];
  } catch {
    return [];
  }
}

function writeSeenQuestions() {
  try {
    window.localStorage.setItem(seenStorageKey(), JSON.stringify(state.seenQuestionIds));
  } catch {
    // The in-page list still works if browser storage is unavailable.
  }
}

function markQuestionSeen(question) {
  if (!question || state.seenQuestionIds.includes(question.id)) {
    updateSeenControls();
    return;
  }
  state.seenQuestionIds.push(question.id);
  writeSeenQuestions();
  updateSeenControls();
}

function seenQuestions() {
  const questionsById = new Map(state.allQuestions.map((question) => [question.id, question]));
  return state.seenQuestionIds.map((id) => questionsById.get(id)).filter(Boolean);
}

function updateSeenControls() {
  const count = state.seenQuestionIds.length;
  if (elements.seenCount) {
    elements.seenCount.textContent = `Seen: ${count}`;
  }
  if (elements.exportSeen) {
    elements.exportSeen.disabled = count === 0;
  }
  if (elements.clearSeen) {
    elements.clearSeen.disabled = count === 0;
  }
}

function clearSeenQuestions() {
  if (!state.seenQuestionIds.length) {
    return;
  }
  const shouldClear = window.confirm(`Clear today's seen list for ${familyTitle}?`);
  if (!shouldClear) {
    return;
  }
  state.seenQuestionIds = [];
  if (state.current) {
    state.seenQuestionIds.push(state.current.id);
  }
  writeSeenQuestions();
  updateSeenControls();
}

function exportSeenQuestions() {
  const questions = seenQuestions();
  if (!questions.length) {
    window.alert("No questions have been seen yet.");
    return;
  }

  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    window.alert("Allow pop-ups for this site, then try exporting again.");
    return;
  }

  const title = `${familyTitle} class review - ${localDateStamp()}`;
  const exportHtml = buildSeenExportDocument(title, questions);

  printWindow.document.open();
  printWindow.document.write(exportHtml);
  printWindow.document.close();
}

function buildSeenExportDocument(title, questions) {
  const questionHtml = questions.map(exportQuestionHtml).join("");

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>${escapeHtml(title)}</title>
    <style>
      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        color: #151711;
        background: white;
        font-family: "Avenir Next", "Gill Sans", "Trebuchet MS", sans-serif;
      }

      main {
        max-width: 960px;
        margin: 0 auto;
        padding: 28px;
      }

      h1 {
        margin: 0 0 4px;
        font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
        font-size: 32px;
      }

      .summary {
        margin: 0 0 28px;
        color: #696452;
        font-weight: 700;
      }

      article {
        break-inside: avoid;
        page-break-inside: avoid;
        margin: 0 0 28px;
        border-top: 2px solid #151711;
        padding-top: 18px;
      }

      h2 {
        margin: 0 0 12px;
        font-size: 20px;
      }

      .meta {
        margin: 0 0 14px;
        color: #696452;
        font-size: 13px;
        font-weight: 800;
      }

      h3 {
        margin: 16px 0 8px;
        color: #083f3a;
        font-size: 13px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }

      img {
        display: block;
        max-width: 100%;
        height: auto;
        border: 1px solid rgba(35, 30, 21, 0.18);
      }

      .actions {
        position: sticky;
        top: 0;
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        padding: 12px 0;
        background: white;
      }

      button {
        min-height: 40px;
        border: 0;
        border-radius: 999px;
        background: #0d695f;
        color: white;
        cursor: pointer;
        font: inherit;
        font-weight: 900;
        padding: 0 16px;
      }

      @media print {
        main {
          max-width: none;
          padding: 0;
        }

        .actions {
          display: none;
        }

        article {
          margin-bottom: 20mm;
        }
      }
    </style>
  </head>
  <body>
    <main>
      <div class="actions">
        <button type="button" onclick="window.print()">Save as PDF</button>
      </div>
      <h1>${escapeHtml(title)}</h1>
      <p class="summary">${questions.length} seen ${questions.length === 1 ? "question" : "questions"} with mark schemes</p>
      ${questionHtml}
    </main>
    <script>
      window.addEventListener("load", () => {
        setTimeout(() => window.print(), 250);
      });
    </script>
  </body>
</html>`;
}

function exportQuestionHtml(question, index) {
  return `<article>
    <h2>${index + 1}. ${escapeHtml(question.paper)} - Question ${escapeHtml(question.questionNumber)}</h2>
    <p class="meta">Topic: ${escapeHtml(formatTopic(topicKeyFor(question)))} | Marks: ${escapeHtml(formatMarksGroup(marksGroupFor(question)))}</p>
    <h3>Question</h3>
    <img src="${escapeHtml(absoluteUrl(question.questionImage))}" alt="${escapeHtml(`${question.paper} question ${question.questionNumber}`)}">
    <h3>Answer / mark scheme</h3>
    <img src="${escapeHtml(absoluteUrl(question.markSchemeImage))}" alt="${escapeHtml(`${question.paper} mark scheme for question ${question.questionNumber}`)}">
  </article>`;
}

function absoluteUrl(url) {
  return new URL(url, window.location.href).href;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function topicKeyFor(question) {
  const route = state.topicRoutes[question.id] || {};
  return forceTopic(route.primary_topic_id || question.topic, question.paperFamily);
}

function forceTopic(value, paperFamily = family) {
  const aliases = topicAliases[paperFamily] || {};
  return aliases[normalizeKey(value)] || defaultTopicFor(paperFamily);
}

function topicTaxonomyFor(paperFamily = family) {
  return topicTaxonomies[paperFamily] || [];
}

function defaultTopicFor(paperFamily = family) {
  return topicTaxonomyFor(paperFamily)[0]?.key || "topic";
}

function formatTopic(topic) {
  return topicLabels[topic] || String(topic || "Topic");
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
  [elements.paperSelect, elements.topicSelect, elements.marksSelect].forEach(syncSelectCountLabels);
}

function applyInitialFilters() {
  setSelectValue(elements.paperSelect, initialFilters.paper);
  refreshDependentFilters();
  setSelectValue(elements.topicSelect, normalizeInitialTopic(initialFilters.topic));
  populateMarksSelect();
  setSelectValue(elements.marksSelect, normalizeInitialMarks(initialFilters.marks));
  syncAllSelectCountLabels();
}

function normalizeInitialTopic(value) {
  if (value === "all") {
    return "all";
  }
  const aliases = topicAliases[family] || {};
  return aliases[normalizeKey(value)] || "all";
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

function topicRoutesFrom(topicData) {
  if (topicData?.records && !Array.isArray(topicData.records)) {
    return topicData.records;
  }
  return {};
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
  if (!normalized || normalized === "unknown" || normalized === "miscellaneous") {
    return "";
  }
  return normalized;
}

function compareTopicKeys(a, b) {
  const topics = topicTaxonomyFor(family);
  const indexA = topics.findIndex((topic) => topic.key === a);
  const indexB = topics.findIndex((topic) => topic.key === b);
  if (indexA !== -1 && indexB !== -1) {
    return indexA - indexB;
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
  refreshDependentFilters({ resetTopic: true, resetMarks: true });
  resetPool({ randomize: false });
});
elements.topicSelect.addEventListener("change", () => {
  syncAllSelectCountLabels();
  refreshDependentFilters({ resetMarks: true });
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
elements.exportSeen?.addEventListener("click", exportSeenQuestions);
elements.clearSeen?.addEventListener("click", clearSeenQuestions);

Promise.all([
  loadFirstJson([`${dataRoot}/question_bank.json`, `${dataRoot}/json/question_bank.json`]),
  loadFirstJson([`${dataRoot}/question_bank.topic_routing.v1.json`, `${dataRoot}/json/question_bank.topic_routing.v1.json`], true),
  imageAvailabilityPath ? loadJson(imageAvailabilityPath, true) : Promise.resolve(null),
])
  .then(([bank, topicData, imageAvailability]) => {
    state.topicRoutes = topicRoutesFrom(topicData);
    state.imageAvailability = imageAvailability;
    state.allQuestions = (bank.questions || [])
      .filter((record) => record.paper_family === family && hasImages(record))
      .map(normalizeQuestion)
      .sort(compareQuestion);
    elements.title.textContent = compactFamilyTitle;
    populatePaperSelect();
    applyInitialFilters();
    loadSeenQuestions();
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
