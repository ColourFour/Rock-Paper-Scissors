const DEFAULT_BANK_PATH = "../../output/json/question_bank.json";

const state = {
  records: [],
  current: null,
};

const ALLOWED_TOPICS_BY_FAMILY = {
  P1: [
    "quadratics",
    "polynomials",
    "partial_fractions",
    "modulus",
    "inequalities",
    "functions",
    "coordinate_geometry",
    "circular_measure",
    "trigonometry",
    "binomial_expansion",
    "differentiation",
    "integration",
    "numerical_methods",
  ],
  P2: ["logarithmic_and_exponential_functions", "trigonometry", "differentiation", "integration"],
  P3: [
    "logarithmic_and_exponential_functions",
    "trigonometry",
    "integration",
    "differentiation",
    "differential_equations",
    "vectors",
    "complex_numbers",
    "series",
    "parametric_equations",
  ],
  P4: [
    "kinematics",
    "forces_and_equilibrium",
    "connected_particles",
    "momentum_and_impulse",
    "work_energy_power",
    "circular_motion",
  ],
  P5: [
    "permutations_and_combinations",
    "probability",
    "discrete_random_variables",
    "binomial_distribution",
    "poisson_distribution",
    "normal_distribution",
    "correlation_and_regression",
  ],
  P6: [
    "probability",
    "continuous_random_variables",
    "normal_distribution",
    "central_limit_theorem",
    "confidence_intervals",
    "hypothesis_testing",
  ],
};

const paperSelect = document.querySelector("#paperSelect");
const topicSelect = document.querySelector("#topicSelect");
const nextButton = document.querySelector("#nextQuestion");
const checkButton = document.querySelector("#checkAnswer");
const fileInput = document.querySelector("#jsonFile");
const statusLine = document.querySelector("#status");
const questionArea = document.querySelector("#questionArea");
const answerArea = document.querySelector("#answerArea");
const paperName = document.querySelector("#paperName");
const topicName = document.querySelector("#topicName");
const questionNumber = document.querySelector("#questionNumber");
const marks = document.querySelector("#marks");
const questionImage = document.querySelector("#questionImage");
const markschemeImage = document.querySelector("#markschemeImage");

function usableRecord(record) {
  return Boolean(
    record &&
      (record.question_image || record.screenshot_path) &&
      record.markscheme_image &&
      (record.paper_name || record.source_pdf)
  );
}

function paperKey(record) {
  return record.paper_name || record.source_pdf || "Unknown paper";
}

function topicKey(record) {
  return record.topic || record.question_level_topic || "unknown";
}

function topicLabel(topic) {
  return topic.replaceAll("_", " ");
}

function familyForPaper(paper) {
  const record = state.records.find((item) => paperKey(item) === paper);
  return record ? record.paper_family || record.question_level_paper_family || "unknown" : "unknown";
}

function imagePath(path) {
  if (!path) return "";
  if (/^(https?:)?\/\//.test(path) || path.startsWith("data:")) return path;
  if (path.startsWith("../../") || path.startsWith("/") || path.startsWith("./")) return path;
  return `../../${path}`;
}

function setStatus(message) {
  statusLine.textContent = message;
}

function loadRecords(records) {
  state.records = records.filter(usableRecord);
  state.current = null;
  answerArea.hidden = true;
  questionArea.hidden = true;

  const papers = [...new Set(state.records.map(paperKey))].sort((a, b) => a.localeCompare(b));
  paperSelect.innerHTML = "";

  for (const paper of papers) {
    const option = document.createElement("option");
    option.value = paper;
    option.textContent = `${paper} (${state.records.filter((record) => paperKey(record) === paper).length})`;
    paperSelect.appendChild(option);
  }

  if (!papers.length) {
    setStatus("No usable records found. Each record needs a question image and a mark scheme image.");
    return;
  }

  updateTopicOptions();
  setStatus(`${state.records.length} questions ready.`);
  showRandomQuestion();
}

function updateTopicOptions() {
  const selectedPaper = paperSelect.value;
  const family = familyForPaper(selectedPaper);
  const recordsForPaper = state.records.filter((record) => paperKey(record) === selectedPaper);
  const presentTopics = new Set(recordsForPaper.map(topicKey));
  const allowedTopics = ALLOWED_TOPICS_BY_FAMILY[family] || [...presentTopics].sort();
  const topics = allowedTopics.filter((topic) => presentTopics.has(topic));

  topicSelect.innerHTML = "";
  for (const topic of topics) {
    const count = recordsForPaper.filter((record) => topicKey(record) === topic).length;
    const option = document.createElement("option");
    option.value = topic;
    option.textContent = `${topicLabel(topic)} (${count})`;
    topicSelect.appendChild(option);
  }

  if (!topics.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No topics available";
    topicSelect.appendChild(option);
  }
}

async function loadDefaultBank() {
  try {
    const response = await fetch(DEFAULT_BANK_PATH, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!Array.isArray(data)) throw new Error("Question bank JSON must be a list.");
    loadRecords(data);
  } catch (error) {
    setStatus("Choose the exported question_bank.json file to begin.");
  }
}

function showRandomQuestion() {
  const selectedPaper = paperSelect.value;
  const selectedTopic = topicSelect.value;
  const choices = state.records.filter((record) => paperKey(record) === selectedPaper && topicKey(record) === selectedTopic);
  if (!choices.length) {
    setStatus("No questions are available for that paper and topic.");
    return;
  }

  const record = choices[Math.floor(Math.random() * choices.length)];
  state.current = record;

  paperName.textContent = paperKey(record);
  topicName.textContent = topicLabel(topicKey(record));
  questionNumber.textContent = `Question ${record.question_number || ""}`.trim();
  marks.textContent = record.marks_if_available ? `${record.marks_if_available} marks` : "Marks not shown";

  questionImage.src = imagePath(record.question_image || record.screenshot_path);
  markschemeImage.src = imagePath(record.markscheme_image);
  answerArea.hidden = true;
  questionArea.hidden = false;
  setStatus("");
}

paperSelect.addEventListener("change", () => {
  updateTopicOptions();
  showRandomQuestion();
});

nextButton.addEventListener("click", showRandomQuestion);

checkButton.addEventListener("click", () => {
  if (!state.current) return;
  answerArea.hidden = false;
});

fileInput.addEventListener("change", async (event) => {
  const file = event.target.files && event.target.files[0];
  if (!file) return;

  try {
    const data = JSON.parse(await file.text());
    if (!Array.isArray(data)) throw new Error("Question bank JSON must be a list.");
    loadRecords(data);
  } catch (error) {
    setStatus(`Could not load JSON: ${error.message}`);
  }
});

loadDefaultBank();
