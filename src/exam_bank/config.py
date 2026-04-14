from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PAPER_FAMILIES = ["P1", "P3", "P4", "P5", "P6", "mixed_or_uncertain"]

DEFAULT_PAPER_FAMILY_TAXONOMY = {
    "P1": {
        "algebra": ["quadratics", "polynomials", "partial_fractions", "modulus", "inequalities", "surds"],
        "functions": ["composite_functions", "inverse_functions", "transformations", "domain_range"],
        "coordinate_geometry": ["straight_line", "circles"],
        "circular_measure": ["radians", "arc_length_sector_area"],
        "trigonometry": ["trig_equations", "trig_identities", "trig_graphs"],
        "series": ["binomial_expansion_positive_integer", "binomial_expansion_fractional_negative"],
        "differentiation": ["standard_differentiation", "tangents_normals", "stationary_points", "connected_rates"],
        "integration": ["standard_integration", "definite_integration", "area_under_curve"],
        "numerical_methods": ["iteration", "estimation_of_roots"],
    },
    "P3": {
        "algebra": ["partial_fractions", "modulus"],
        "logarithmic_and_exponential_functions": ["log_laws", "exponential_equations", "logarithmic_equations"],
        "trigonometry": ["trig_substitutions", "trig_equations", "identities"],
        "calculus": [
            "integration_by_parts",
            "integration_by_substitution",
            "partial_fractions_integration",
            "recurrence_by_integration",
            "differential_equations",
            "implicit_differentiation",
            "parametric_differentiation",
            "parametric_integration",
        ],
        "vectors": ["vector_geometry", "lines_vectors"],
        "complex_numbers": ["argand_diagrams", "modulus_argument", "roots_of_complex_numbers"],
        "series": ["binomial_expansion_fractional_negative", "maclaurin_series"],
        "differential_equations": ["separable", "first_order_modelling"],
    },
    "P4": {
        "kinematics": ["constant_acceleration", "displacement_velocity_acceleration", "velocity_time_graphs"],
        "dynamics": ["newtons_laws", "connected_particles", "pulleys"],
        "forces_and_equilibrium": ["resolving_forces", "friction", "limiting_equilibrium"],
        "momentum": ["impulse", "collisions"],
        "work_energy_power": ["work", "kinetic_potential_energy", "power"],
        "motion_in_a_circle": ["centripetal_force"],
        "variable_force": ["differential_equation_modelling"],
    },
    "P5": {
        "data_representation": ["tables_charts", "histograms", "box_plots", "cumulative_frequency"],
        "permutations_and_combinations": ["counting_principles", "arrangements", "selections"],
        "probability": ["basic_probability", "conditional_probability", "independent_events", "tree_diagrams"],
        "discrete_random_variables": ["expectation", "variance"],
        "binomial_distribution": ["direct_binomial", "cumulative_binomial"],
        "poisson_distribution": ["direct_poisson", "poisson_modelling"],
        "normal_distribution": ["standardisation", "inverse_normal"],
        "sampling_and_estimation": ["sample_mean", "unbiased_estimators"],
        "correlation_and_regression": ["product_moment_correlation", "least_squares_regression", "interpretation"],
    },
    "P6": {
        "probability": ["conditional_probability", "bayes"],
        "discrete_random_variables": ["expectation_variance", "generating_or_combining_variables"],
        "continuous_random_variables": ["density_functions", "expectation_variance"],
        "normal_distribution": ["linear_combinations"],
        "central_limit_theorem": ["approximation_using_clt"],
        "confidence_intervals": ["population_mean"],
        "hypothesis_testing": ["binomial", "poisson", "normal", "paired_or_unpaired_context_if_relevant"],
    },
    "mixed_or_uncertain": {},
}


def _phrase(label: str) -> str:
    return label.replace("_", " ")


def _flatten_topic_taxonomy(taxonomy: dict[str, dict[str, list[str]]]) -> dict[str, list[str]]:
    flattened: dict[str, list[str]] = {}
    for family, topics in taxonomy.items():
        if family == "mixed_or_uncertain":
            continue
        for topic, subtopics in topics.items():
            flattened.setdefault(topic, [])
            for subtopic in subtopics:
                if subtopic not in flattened[topic]:
                    flattened[topic].append(subtopic)
    return flattened


def _auto_classification_hints(
    taxonomy: dict[str, dict[str, list[str]]],
) -> dict[str, dict[str, dict[str, dict[str, list[str]]]]]:
    hints: dict[str, dict[str, dict[str, dict[str, list[str]]]]] = {}
    for family, topics in taxonomy.items():
        if family == "mixed_or_uncertain":
            continue
        hints[family] = {}
        for topic, subtopics in topics.items():
            hints[family][topic] = {}
            topic_phrase = _phrase(topic)
            for subtopic in subtopics:
                subtopic_phrase = _phrase(subtopic)
                tokens = [token for token in subtopic.split("_") if len(token) >= 4]
                hints[family][topic][subtopic] = {
                    "methods": [],
                    "objects": [subtopic_phrase, topic_phrase],
                    "keywords": tokens,
                }
    return hints


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


MANUAL_CLASSIFICATION_HINTS = {
    "P1": {
        "algebra": {
            "quadratics": {"methods": ["solve", "factorise", "complete the square"], "objects": ["quadratic equation", "quadratic"], "keywords": ["discriminant", "roots"]},
            "polynomials": {"methods": ["factorise", "divide", "show"], "objects": ["polynomial"], "keywords": ["remainder", "factor theorem"]},
            "partial_fractions": {"methods": ["partial fractions", "express.*partial fractions"], "objects": ["rational function", "proper fraction"], "keywords": ["denominator", "numerator"]},
            "modulus": {"methods": ["solve", "sketch"], "objects": ["modulus"], "keywords": ["|x|", "absolute value"]},
            "inequalities": {"methods": ["solve"], "objects": ["inequality"], "keywords": ["<", ">", "<=", ">="]},
            "surds": {"methods": ["simplify", "rationalise"], "objects": ["surd"], "keywords": ["sqrt", "root"]},
        },
        "functions": {
            "composite_functions": {"methods": ["find", "show"], "objects": ["composite function"], "keywords": ["fg", "gf", "f(g", "g(f"]},
            "inverse_functions": {"methods": ["find"], "objects": ["inverse function"], "keywords": ["inverse", "f^{-1}"]},
            "transformations": {"methods": ["sketch", "transform", "describe"], "objects": ["function"], "keywords": ["translation", "stretch", "reflection"]},
            "domain_range": {"methods": ["state", "find"], "objects": ["domain", "range"], "keywords": ["one-one"]},
        },
        "coordinate_geometry": {
            "straight_line": {"methods": ["find the equation", "show"], "objects": ["straight line", "gradient"], "keywords": ["perpendicular", "parallel"]},
            "circles": {"methods": ["find the equation", "show"], "objects": ["circle", "radius", "centre"], "keywords": ["diameter", "tangent"]},
        },
        "circular_measure": {
            "radians": {"methods": ["find", "calculate"], "objects": ["radian"], "keywords": ["theta"]},
            "arc_length_sector_area": {"methods": ["find", "calculate"], "objects": ["arc", "sector"], "keywords": ["arc length", "sector area"]},
        },
        "trigonometry": {
            "trig_equations": {"methods": ["solve"], "objects": ["trigonometric equation"], "keywords": ["sin", "cos", "tan"]},
            "trig_identities": {"methods": ["prove", "show"], "objects": ["identity"], "keywords": ["sin", "cos", "tan"]},
            "trig_graphs": {"methods": ["sketch", "draw"], "objects": ["trig graph"], "keywords": ["sin", "cos", "tan"]},
        },
        "series": {
            "binomial_expansion_positive_integer": {"methods": ["expand"], "objects": ["binomial"], "keywords": ["ascending powers", "positive integer"]},
            "binomial_expansion_fractional_negative": {"methods": ["expand", "approximate"], "objects": ["negative power", "fractional power"], "keywords": ["ascending powers", "valid for"]},
        },
        "differentiation": {
            "standard_differentiation": {"methods": ["differentiate", "find dy/dx"], "objects": ["derivative"], "keywords": ["gradient"]},
            "tangents_normals": {"methods": ["find the equation"], "objects": ["tangent", "normal"], "keywords": ["gradient"]},
            "stationary_points": {"methods": ["find", "determine"], "objects": ["stationary point"], "keywords": ["maximum", "minimum"]},
            "connected_rates": {"methods": ["differentiate"], "objects": ["rate of change"], "keywords": ["connected rates"]},
        },
        "integration": {
            "standard_integration": {"methods": ["integrate", "find the integral"], "objects": ["integral"], "keywords": ["constant of integration"]},
            "definite_integration": {"methods": ["evaluate", "integrate"], "objects": ["definite integral"], "keywords": ["limits"]},
            "area_under_curve": {"methods": ["find the area", "calculate the area"], "objects": ["curve"], "keywords": ["area under"]},
        },
        "numerical_methods": {
            "iteration": {"methods": ["iterate", "iteration"], "objects": ["recurrence"], "keywords": ["x_n", "x_{n+1}"]},
            "estimation_of_roots": {"methods": ["estimate", "find"], "objects": ["root"], "keywords": ["change of sign"]},
        },
    },
    "P3": {
        "algebra": {
            "partial_fractions": {"methods": ["partial fractions", "express.*partial fractions"], "objects": ["rational function"], "keywords": ["denominator", "numerator"]},
            "modulus": {"methods": ["solve", "sketch"], "objects": ["modulus"], "keywords": ["|x|"]},
        },
        "logarithmic_and_exponential_functions": {
            "log_laws": {"methods": ["simplify", "show"], "objects": ["logarithm"], "keywords": ["log", "ln"]},
            "exponential_equations": {"methods": ["solve"], "objects": ["exponential equation"], "keywords": ["e^", "exp"]},
            "logarithmic_equations": {"methods": ["solve"], "objects": ["logarithmic equation"], "keywords": ["log", "ln"]},
        },
        "trigonometry": {
            "trig_substitutions": {"methods": ["substitution"], "objects": ["trigonometric"], "keywords": ["sin", "cos", "tan"]},
            "trig_equations": {"methods": ["solve"], "objects": ["trigonometric equation"], "keywords": ["sin", "cos", "tan"]},
            "identities": {"methods": ["prove", "show"], "objects": ["identity"], "keywords": ["sec", "cosec", "cot"]},
        },
        "calculus": {
            "integration_by_parts": {"methods": ["integration by parts", "integrate"], "objects": ["x sec", "x sin", "x cos", "x e", "product requiring parts"], "keywords": ["sec^2", "ln"]},
            "integration_by_substitution": {"methods": ["substitution", "using the substitution"], "objects": ["integral"], "keywords": ["u ="]},
            "partial_fractions_integration": {"methods": ["integrate"], "objects": ["partial fractions"], "keywords": ["rational function"]},
            "recurrence_by_integration": {"methods": ["show", "prove"], "objects": ["recurrence relation", "integral"], "keywords": ["I_n", "I_{n+1}"]},
            "differential_equations": {"methods": ["solve", "form"], "objects": ["differential equation"], "keywords": ["dy/dx"]},
            "implicit_differentiation": {"methods": ["differentiate", "find dy/dx"], "objects": ["implicit"], "keywords": ["implicitly"]},
            "parametric_differentiation": {"methods": ["differentiate", "find dy/dx"], "objects": ["parametric"], "keywords": ["dx/dt", "dy/dt"]},
            "parametric_integration": {"methods": ["integrate"], "objects": ["parametric"], "keywords": ["dx/dt"]},
        },
        "vectors": {
            "vector_geometry": {"methods": ["prove", "show", "find"], "objects": ["vector"], "keywords": ["parallel", "perpendicular"]},
            "lines_vectors": {"methods": ["find", "show"], "objects": ["vector equation", "line"], "keywords": ["scalar product"]},
        },
        "complex_numbers": {
            "argand_diagrams": {"methods": ["sketch", "represent"], "objects": ["argand diagram"], "keywords": ["complex"]},
            "modulus_argument": {"methods": ["find", "calculate"], "objects": ["modulus", "argument"], "keywords": ["arg", "|z|"]},
            "roots_of_complex_numbers": {"methods": ["solve", "find the roots"], "objects": ["complex roots"], "keywords": ["z"]},
        },
        "series": {
            "binomial_expansion_fractional_negative": {"methods": ["expand", "approximate"], "objects": ["negative power", "fractional power"], "keywords": ["ascending powers", "valid for"]},
            "maclaurin_series": {"methods": ["expand", "find"], "objects": ["maclaurin series"], "keywords": ["powers of x"]},
        },
        "differential_equations": {
            "separable": {"methods": ["separate variables", "solve"], "objects": ["differential equation"], "keywords": ["dy/dx"]},
            "first_order_modelling": {"methods": ["model", "form", "solve"], "objects": ["differential equation"], "keywords": ["rate of change"]},
        },
    },
    "P4": {
        "kinematics": {
            "constant_acceleration": {"methods": ["find", "calculate"], "objects": ["constant acceleration"], "keywords": ["suvat"]},
            "displacement_velocity_acceleration": {"methods": ["differentiate", "integrate", "find"], "objects": ["displacement", "velocity", "acceleration"], "keywords": ["particle"]},
            "velocity_time_graphs": {"methods": ["sketch", "find"], "objects": ["velocity-time graph"], "keywords": ["area under"]},
        },
        "dynamics": {
            "newtons_laws": {"methods": ["apply", "find"], "objects": ["force", "acceleration"], "keywords": ["newton's second law", "f = ma"]},
            "connected_particles": {"methods": ["find", "calculate"], "objects": ["connected particles"], "keywords": ["tension", "pulley"]},
            "pulleys": {"methods": ["find", "calculate"], "objects": ["pulley"], "keywords": ["tension"]},
        },
        "forces_and_equilibrium": {
            "resolving_forces": {"methods": ["resolve", "find"], "objects": ["force"], "keywords": ["component"]},
            "friction": {"methods": ["find", "calculate"], "objects": ["friction"], "keywords": ["coefficient of friction"]},
            "limiting_equilibrium": {"methods": ["find", "calculate"], "objects": ["limiting equilibrium"], "keywords": ["about to move"]},
        },
        "momentum": {
            "impulse": {"methods": ["find", "calculate"], "objects": ["impulse"], "keywords": ["momentum"]},
            "collisions": {"methods": ["find", "calculate"], "objects": ["collision"], "keywords": ["coefficient of restitution"]},
        },
        "work_energy_power": {
            "work": {"methods": ["find", "calculate"], "objects": ["work"], "keywords": ["force times distance"]},
            "kinetic_potential_energy": {"methods": ["find", "calculate"], "objects": ["kinetic energy", "potential energy"], "keywords": ["energy"]},
            "power": {"methods": ["find", "calculate"], "objects": ["power"], "keywords": ["rate of working"]},
        },
        "motion_in_a_circle": {
            "centripetal_force": {"methods": ["find", "calculate"], "objects": ["centripetal force"], "keywords": ["circular motion"]},
        },
        "variable_force": {
            "differential_equation_modelling": {"methods": ["form", "solve"], "objects": ["variable force", "differential equation"], "keywords": ["resistance"]},
        },
    },
    "P5": {
        "data_representation": {
            "tables_charts": {"methods": ["interpret", "draw"], "objects": ["table", "chart"], "keywords": ["frequency"]},
            "histograms": {"methods": ["draw", "find"], "objects": ["histogram"], "keywords": ["frequency density"]},
            "box_plots": {"methods": ["draw", "interpret"], "objects": ["box plot"], "keywords": ["quartile", "median"]},
            "cumulative_frequency": {"methods": ["draw", "estimate"], "objects": ["cumulative frequency"], "keywords": ["percentile"]},
        },
        "permutations_and_combinations": {
            "counting_principles": {"methods": ["count", "find"], "objects": ["arrangements"], "keywords": ["ways"]},
            "arrangements": {"methods": ["arrange"], "objects": ["permutation"], "keywords": ["letters"]},
            "selections": {"methods": ["select", "choose"], "objects": ["combination"], "keywords": ["committee"]},
        },
        "probability": {
            "basic_probability": {"methods": ["find", "calculate"], "objects": ["probability"], "keywords": ["P("]},
            "conditional_probability": {"methods": ["find", "calculate"], "objects": ["conditional probability"], "keywords": ["given that"]},
            "independent_events": {"methods": ["show", "find"], "objects": ["independent events"], "keywords": ["independent"]},
            "tree_diagrams": {"methods": ["draw", "use"], "objects": ["tree diagram"], "keywords": ["branch"]},
        },
        "discrete_random_variables": {
            "expectation": {"methods": ["find", "calculate"], "objects": ["expected value"], "keywords": ["E("]},
            "variance": {"methods": ["find", "calculate"], "objects": ["variance"], "keywords": ["Var"]},
        },
        "binomial_distribution": {
            "direct_binomial": {"methods": ["find", "calculate"], "objects": ["binomial distribution"], "keywords": ["X ~ B", "Bin"]},
            "cumulative_binomial": {"methods": ["find", "calculate"], "objects": ["binomial distribution"], "keywords": ["at most", "at least"]},
        },
        "poisson_distribution": {
            "direct_poisson": {"methods": ["find", "calculate"], "objects": ["poisson distribution"], "keywords": ["Poisson"]},
            "poisson_modelling": {"methods": ["model", "find"], "objects": ["poisson distribution"], "keywords": ["mean rate"]},
        },
        "normal_distribution": {
            "standardisation": {"methods": ["find", "calculate"], "objects": ["normal distribution"], "keywords": ["standardise", "standard deviation"]},
            "inverse_normal": {"methods": ["find"], "objects": ["normal distribution"], "keywords": ["inverse normal", "percentage point"]},
        },
        "sampling_and_estimation": {
            "sample_mean": {"methods": ["find", "calculate"], "objects": ["sample mean"], "keywords": ["sample"]},
            "unbiased_estimators": {"methods": ["show", "find"], "objects": ["unbiased estimator"], "keywords": ["estimator"]},
        },
        "correlation_and_regression": {
            "product_moment_correlation": {"methods": ["find", "calculate"], "objects": ["correlation"], "keywords": ["product moment"]},
            "least_squares_regression": {"methods": ["find", "calculate"], "objects": ["regression line"], "keywords": ["least squares"]},
            "interpretation": {"methods": ["interpret", "comment"], "objects": ["correlation", "regression"], "keywords": ["context"]},
        },
    },
    "P6": {
        "probability": {
            "conditional_probability": {"methods": ["find", "calculate"], "objects": ["conditional probability"], "keywords": ["given that"]},
            "bayes": {"methods": ["use", "find"], "objects": ["Bayes"], "keywords": ["posterior"]},
        },
        "discrete_random_variables": {
            "expectation_variance": {"methods": ["find", "calculate"], "objects": ["expectation", "variance"], "keywords": ["E(", "Var"]},
            "generating_or_combining_variables": {"methods": ["find", "derive"], "objects": ["random variables"], "keywords": ["independent"]},
        },
        "continuous_random_variables": {
            "density_functions": {"methods": ["find", "show"], "objects": ["probability density function"], "keywords": ["pdf", "density"]},
            "expectation_variance": {"methods": ["find", "calculate"], "objects": ["expectation", "variance"], "keywords": ["integral"]},
        },
        "normal_distribution": {
            "linear_combinations": {"methods": ["find", "calculate"], "objects": ["linear combination"], "keywords": ["normal distribution"]},
        },
        "central_limit_theorem": {
            "approximation_using_clt": {"methods": ["approximate", "find"], "objects": ["central limit theorem"], "keywords": ["large sample"]},
        },
        "confidence_intervals": {
            "population_mean": {"methods": ["find", "construct"], "objects": ["confidence interval"], "keywords": ["population mean"]},
        },
        "hypothesis_testing": {
            "binomial": {"methods": ["test"], "objects": ["binomial distribution"], "keywords": ["hypothesis", "significance"]},
            "poisson": {"methods": ["test"], "objects": ["poisson distribution"], "keywords": ["hypothesis", "significance"]},
            "normal": {"methods": ["test"], "objects": ["normal distribution"], "keywords": ["hypothesis", "significance"]},
            "paired_or_unpaired_context_if_relevant": {"methods": ["test"], "objects": ["paired", "unpaired"], "keywords": ["hypothesis"]},
        },
    },
}

DEFAULT_TOPIC_TAXONOMY = _flatten_topic_taxonomy(DEFAULT_PAPER_FAMILY_TAXONOMY)
DEFAULT_CLASSIFICATION_HINTS = _deep_merge_dicts(
    _auto_classification_hints(DEFAULT_PAPER_FAMILY_TAXONOMY),
    MANUAL_CLASSIFICATION_HINTS,
)
DEFAULT_TOPICS = list(DEFAULT_TOPIC_TAXONOMY)

DIFFICULTY_LABELS = ["easy", "average", "difficult"]


@dataclass
class InputConfig:
    question_papers_dir: Path = Path("input/question_papers")
    mark_schemes_dir: Path = Path("input/mark_schemes")
    mappings_dir: Path = Path("input/mappings")


@dataclass
class OutputConfig:
    images_dir: Path = Path("output/images")
    json_dir: Path = Path("output/json")
    csv_dir: Path = Path("output/csv")
    review_dir: Path = Path("output/review")
    debug_dir: Path = Path("output/debug")


@dataclass
class DetectionConfig:
    max_question_number: int = 30
    question_start_max_x: float = 115
    min_question_start_y: float = 65
    bottom_margin: float = 45
    crop_left_margin: float = 35
    crop_right_margin: float = 35
    crop_top_margin: float = 45
    crop_bottom_margin: float = 40
    crop_padding: float = 10
    min_text_chars_per_page: int = 25
    min_question_chars: int = 20
    render_dpi: int = 220
    stitch_gap_px: int = 18
    output_mode: str = "prompt_only"
    image_mode: str | None = None
    anchor_min_confidence: float = 0.58
    anchor_left_tolerance: float = 12
    anchor_font_size_ratio: float = 0.85
    anchor_y_tolerance: float = 8
    span_line_y_tolerance: float = 6
    continuation_min_text_chars: int = 8
    prompt_region_max_gap: float = 80
    prompt_graphic_lookahead: float = 180
    prompt_graphic_overlap_padding: float = 24
    min_crop_height: float = 24
    max_crop_height_ratio: float = 0.82


@dataclass
class OCRConfig:
    enabled: bool = True
    language: str = "eng"
    dpi: int = 220
    min_confidence: int = 45


@dataclass
class NamingConfig:
    image_template: str = "{paper_name}_q{question_number:02d}.png"
    json_name: str = "question_bank.json"
    csv_name: str = "question_bank.csv"
    review_name: str = "review_items.csv"


@dataclass
class ClassificationConfig:
    enable_openai: bool = False
    openai_model: str = "gpt-5-mini"
    openai_timeout_seconds: int = 30
    uncertainty_threshold: float = 0.55


@dataclass
class TopicPDFConfig:
    enable_topic_pdfs: bool = False
    topic_pdf_output_dir: Path = Path("output/topic_pdfs")
    page_size: str = "A4"
    margin: float = 42
    image_max_width: float = 500
    caption_font_size: float = 8
    section_heading_font_size: float = 15
    topic_title_font_size: float = 22


@dataclass
class DebugConfig:
    enabled: bool = False
    save_rendered_pages: bool = True
    save_text_boxes: bool = True
    save_anchor_candidates: bool = True
    save_proposed_boxes: bool = True
    save_crop_boxes: bool = True


@dataclass
class AppConfig:
    input: InputConfig = field(default_factory=InputConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    paper_families: list[str] = field(default_factory=lambda: list(PAPER_FAMILIES))
    paper_family_taxonomy: dict[str, dict[str, list[str]]] = field(
        default_factory=lambda: {
            family: {topic: list(subtopics) for topic, subtopics in topics.items()}
            for family, topics in DEFAULT_PAPER_FAMILY_TAXONOMY.items()
        }
    )
    topics: list[str] = field(default_factory=lambda: list(DEFAULT_TOPICS))
    topic_taxonomy: dict[str, list[str]] = field(default_factory=lambda: {key: list(value) for key, value in DEFAULT_TOPIC_TAXONOMY.items()})
    classification_hints: dict[str, dict[str, dict[str, dict[str, list[str]]]]] = field(
        default_factory=lambda: {
            family: {
                topic: {subtopic: {kind: list(values) for kind, values in hints.items()} for subtopic, hints in subtopics.items()}
                for topic, subtopics in topics.items()
            }
            for family, topics in DEFAULT_CLASSIFICATION_HINTS.items()
        }
    )
    difficulty_labels: list[str] = field(default_factory=lambda: list(DIFFICULTY_LABELS))
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    ocr: OCRConfig = field(default_factory=OCRConfig)
    naming: NamingConfig = field(default_factory=NamingConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)
    topic_pdfs: TopicPDFConfig = field(default_factory=TopicPDFConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)

    def ensure_output_dirs(self) -> None:
        for directory in [
            self.output.images_dir,
            self.output.json_dir,
            self.output.csv_dir,
            self.output.review_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)
        if self.debug.enabled:
            self.output.debug_dir.mkdir(parents=True, exist_ok=True)
        if self.topic_pdfs.enable_topic_pdfs:
            self.topic_pdfs.topic_pdf_output_dir.mkdir(parents=True, exist_ok=True)


def load_config(path: str | Path | None = None) -> AppConfig:
    config = AppConfig()
    config_path = Path(path) if path else Path("config.yaml")
    if not config_path.exists():
        validate_config(config)
        return config

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to read config.yaml. Run `pip install -r requirements.txt`.") from exc

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {config_path}")

    _apply_mapping(config, raw)
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    if config.paper_families != PAPER_FAMILIES:
        raise ValueError(f"Paper families must be exactly {PAPER_FAMILIES}.")
    for family in config.paper_family_taxonomy:
        if family not in config.paper_families:
            raise ValueError(f"paper_family_taxonomy contains unknown paper family `{family}`.")
    for family in config.paper_families:
        config.paper_family_taxonomy.setdefault(family, {})

    for family, topics in config.paper_family_taxonomy.items():
        if family != "mixed_or_uncertain" and (not isinstance(topics, dict) or not topics):
            raise ValueError(f"paper_family_taxonomy.{family} must contain at least one topic.")
        if not isinstance(topics, dict):
            raise ValueError(f"paper_family_taxonomy.{family} must be a mapping.")
        for topic, subtopics in topics.items():
            if not isinstance(topic, str) or not topic.strip():
                raise ValueError(f"Every topic label for {family} must be a non-empty string.")
            if not isinstance(subtopics, list) or not subtopics:
                raise ValueError(f"paper_family_taxonomy.{family}.{topic} must contain at least one subtopic.")
            for subtopic in subtopics:
                if not isinstance(subtopic, str) or not subtopic.strip():
                    raise ValueError(f"Every subtopic for {family}.{topic} must be a non-empty string.")

    config.topic_taxonomy = _flatten_topic_taxonomy(config.paper_family_taxonomy)
    config.topics = list(config.topic_taxonomy)

    for family, topics in config.classification_hints.items():
        if family not in config.paper_family_taxonomy:
            raise ValueError(f"classification_hints contains unknown paper family `{family}`.")
        if not isinstance(topics, dict):
            raise ValueError(f"classification_hints.{family} must be a mapping.")
        for topic, subtopics in topics.items():
            if topic not in config.paper_family_taxonomy[family]:
                raise ValueError(f"classification_hints.{family} contains unknown topic `{topic}`.")
            if not isinstance(subtopics, dict):
                raise ValueError(f"classification_hints.{family}.{topic} must be a mapping.")
            for subtopic, hints in subtopics.items():
                if subtopic not in config.paper_family_taxonomy[family][topic]:
                    raise ValueError(f"classification_hints.{family}.{topic} contains unknown subtopic `{subtopic}`.")
                _validate_hint_groups(hints, f"classification_hints.{family}.{topic}.{subtopic}")

    if config.difficulty_labels != DIFFICULTY_LABELS:
        raise ValueError(f"Difficulty labels must be exactly {DIFFICULTY_LABELS}.")
    if not 0 <= config.classification.uncertainty_threshold <= 1:
        raise ValueError("classification.uncertainty_threshold must be between 0 and 1.")
    if config.detection.output_mode not in {"prompt_only", "full_region"}:
        raise ValueError("detection.output_mode must be `prompt_only` or `full_region`.")
    if config.detection.image_mode not in {None, "prompt_crop", "pdf_crop"}:
        raise ValueError("detection.image_mode must be `prompt_crop`, `pdf_crop`, or unset.")
    if config.detection.image_mode == "pdf_crop":
        config.detection.output_mode = "full_region"
    elif config.detection.image_mode == "prompt_crop":
        config.detection.output_mode = "prompt_only"
    if not 0 < config.detection.max_crop_height_ratio <= 1:
        raise ValueError("detection.max_crop_height_ratio must be between 0 and 1.")
    if config.topic_pdfs.page_size.upper() not in {"A4", "LETTER"}:
        raise ValueError("topic_pdfs.page_size must be `A4` or `LETTER`.")
    if config.topic_pdfs.margin < 0:
        raise ValueError("topic_pdfs.margin must be non-negative.")
    if config.topic_pdfs.image_max_width <= 0:
        raise ValueError("topic_pdfs.image_max_width must be positive.")
    if config.topic_pdfs.caption_font_size <= 0:
        raise ValueError("topic_pdfs.caption_font_size must be positive.")
    if config.topic_pdfs.section_heading_font_size <= 0:
        raise ValueError("topic_pdfs.section_heading_font_size must be positive.")
    if config.topic_pdfs.topic_title_font_size <= 0:
        raise ValueError("topic_pdfs.topic_title_font_size must be positive.")


def _validate_hint_groups(hints: Any, location: str) -> None:
    if not isinstance(hints, dict):
        raise ValueError(f"{location} must be a mapping.")
    for hint_kind, patterns in hints.items():
        if hint_kind not in {"methods", "objects", "keywords"}:
            raise ValueError(f"{location} contains unknown hint group `{hint_kind}`.")
        if not isinstance(patterns, list) or not all(isinstance(pattern, str) for pattern in patterns):
            raise ValueError(f"{location}.{hint_kind} must be a list of strings.")


def _apply_mapping(config: AppConfig, raw: dict[str, Any]) -> None:
    for key, value in raw.items():
        if key in {"input", "output", "detection", "ocr", "naming", "classification", "topic_pdfs", "debug"}:
            target = getattr(config, key)
            if not isinstance(value, dict):
                raise ValueError(f"Config section `{key}` must be a mapping.")
            _set_dataclass_fields(target, value, path_fields=key in {"input", "output"})
            if key == "topic_pdfs" and "topic_pdf_output_dir" in value:
                target.topic_pdf_output_dir = Path(target.topic_pdf_output_dir)
        elif key == "classification_hints":
            if not isinstance(value, dict):
                raise ValueError("Config section `classification_hints` must be a mapping.")
            config.classification_hints = _deep_merge_dicts(config.classification_hints, value)
        elif key == "paper_family_taxonomy":
            if not isinstance(value, dict):
                raise ValueError("Config section `paper_family_taxonomy` must be a mapping.")
            config.paper_family_taxonomy = value
        elif key in {"paper_families", "topics", "topic_taxonomy", "difficulty_labels"}:
            setattr(config, key, value)
        else:
            raise ValueError(f"Unknown config key `{key}`.")


def _set_dataclass_fields(target: object, values: dict[str, Any], path_fields: bool = False) -> None:
    valid = set(target.__dataclass_fields__)  # type: ignore[attr-defined]
    for key, value in values.items():
        if key not in valid:
            raise ValueError(f"Unknown config key `{key}` in {target.__class__.__name__}.")
        if path_fields:
            value = Path(value)
        setattr(target, key, value)
