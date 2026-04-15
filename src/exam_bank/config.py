from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PAPER_FAMILIES = ["P1", "P2", "P3", "P4", "P5", "P6", "unknown"]

DEFAULT_PAPER_FAMILY_TAXONOMY = {
    "P1": {
        "quadratics": ["general"],
        "polynomials": ["general"],
        "partial_fractions": ["general"],
        "modulus": ["general"],
        "inequalities": ["general"],
        "functions": ["general"],
        "coordinate_geometry": ["general"],
        "circular_measure": ["general"],
        "trigonometry": ["general"],
        "binomial_expansion": ["general"],
        "differentiation": ["general"],
        "integration": ["general"],
        "numerical_methods": ["general"],
    },
    "P2": {
        "logarithmic_and_exponential_functions": ["general"],
        "trigonometry": ["general"],
        "differentiation": ["general"],
        "integration": ["general"],
    },
    "P3": {
        "logarithmic_and_exponential_functions": ["general"],
        "trigonometry": ["general"],
        "integration": ["general"],
        "differentiation": ["general"],
        "differential_equations": ["general"],
        "vectors": ["general"],
        "complex_numbers": ["general"],
        "series": ["general"],
        "parametric_equations": ["general"],
    },
    "P4": {
        "kinematics": ["general"],
        "forces_and_equilibrium": ["general"],
        "connected_particles": ["general"],
        "momentum_and_impulse": ["general"],
        "work_energy_power": ["general"],
        "circular_motion": ["general"],
    },
    "P5": {
        "permutations_and_combinations": ["general"],
        "probability": ["general"],
        "discrete_random_variables": ["general"],
        "binomial_distribution": ["general"],
        "poisson_distribution": ["general"],
        "normal_distribution": ["general"],
        "correlation_and_regression": ["general"],
    },
    "P6": {
        "probability": ["general"],
        "continuous_random_variables": ["general"],
        "normal_distribution": ["general"],
        "central_limit_theorem": ["general"],
        "confidence_intervals": ["general"],
        "hypothesis_testing": ["general"],
    },
    "unknown": {},
}


def _phrase(label: str) -> str:
    return label.replace("_", " ")


def _flatten_topic_taxonomy(taxonomy: dict[str, dict[str, list[str]]]) -> dict[str, list[str]]:
    flattened: dict[str, list[str]] = {}
    for family, topics in taxonomy.items():
        if family == "unknown":
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
        if family == "unknown":
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


CAIE_9709_HINTS = {
    "paper_family_aliases": {
        "1": "P1",
        "3": "P3",
        "4": "P4",
        "5": "P5",
        "paper 1": "P1",
        "paper 3": "P3",
        "paper 4": "P4",
        "paper 5": "P5",
        "pure mathematics 1": "P1",
        "pure mathematics 3": "P3",
        "mechanics": "P4",
        "probability & statistics 1": "P5",
        "probability and statistics 1": "P5",
        "m1": "P4",
        "s1": "P5",
    },

    "P1": {
        "quadratics": {
            "subtopics": {
                "solving": {
                    "methods": ["solve", "find the roots", "factorise", "complete the square"],
                    "keywords": ["quadratic", "root", "roots", "discriminant", "equal roots", "real roots"],
                    "anti_keywords": ["log", "ln", "vector", "complex", "probability"],
                },
                "discriminant": {
                    "methods": ["show", "determine", "find"],
                    "keywords": ["discriminant", "equal roots", "real and distinct", "no real roots"],
                },
            },
        },
        "polynomials": {
            "subtopics": {
                "remainder_factor_theorem": {
                    "methods": ["find", "show", "determine", "factorise"],
                    "keywords": ["remainder", "factor theorem", "when f(x) is divided by", "is a factor of"],
                },
                "division": {
                    "methods": ["divide", "express"],
                    "keywords": ["quotient", "remainder", "divided by"],
                },
            },
        },
        "partial_fractions": {
            "subtopics": {
                "decomposition": {
                    "methods": ["express in partial fractions", "decompose"],
                    "keywords": ["partial fractions", "rational function"],
                },
            },
        },
        "modulus": {
            "subtopics": {
                "equations": {
                    "methods": ["solve"],
                    "keywords": ["|x|", "modulus", "absolute value"],
                },
                "graphs": {
                    "methods": ["sketch", "draw"],
                    "keywords": ["|x|", "modulus", "graph"],
                },
            },
        },
        "inequalities": {
            "subtopics": {
                "algebraic": {
                    "methods": ["solve"],
                    "keywords": ["inequality", "<", ">", "≤", "≥"],
                    "anti_keywords": ["probability", "hypothesis"],
                },
            },
        },
        "functions": {
            "subtopics": {
                "composite": {
                    "methods": ["find", "show"],
                    "keywords": ["f(g(x))", "g(f(x))", "fg", "gf", "composite"],
                },
                "inverse": {
                    "methods": ["find", "show"],
                    "keywords": ["inverse", "f^-1", "f^{-1}"],
                },
                "transformations": {
                    "methods": ["sketch", "describe", "write down"],
                    "keywords": ["translation", "stretch", "reflection", "transformation"],
                },
                "domain_range": {
                    "methods": ["state", "find"],
                    "keywords": ["domain", "range", "one-one"],
                },
            },
        },
        "coordinate_geometry": {
            "subtopics": {
                "straight_line": {
                    "methods": ["find the equation", "show that"],
                    "keywords": ["gradient", "parallel", "perpendicular", "midpoint"],
                },
            },
        },
        "circular_measure": {
            "subtopics": {
                "radians": {
                    "methods": ["find", "calculate"],
                    "keywords": ["radian", "θ", "theta"],
                },
                "arc_sector": {
                    "methods": ["find", "calculate"],
                    "keywords": ["arc length", "sector area", "sector"],
                },
            },
        },
        "trigonometry": {
            "subtopics": {
                "equations": {
                    "methods": ["solve"],
                    "keywords": ["sin", "cos", "tan"],
                },
                "identities": {
                    "methods": ["show that", "prove that"],
                    "keywords": ["identity", "sin", "cos", "tan"],
                },
                "graphs": {
                    "methods": ["sketch", "draw"],
                    "keywords": ["amplitude", "period", "trigonometric graph", "sin", "cos", "tan"],
                },
            },
        },
        "binomial_expansion": {
            "subtopics": {
                "positive_integer": {
                    "methods": ["expand"],
                    "keywords": ["binomial", "positive integer power"],
                },
                "fractional_negative": {
                    "methods": ["expand", "approximate"],
                    "keywords": ["ascending powers", "valid for", "fractional power", "negative power"],
                },
            },
        },
        "differentiation": {
            "subtopics": {
                "standard": {
                    "methods": ["differentiate", "find dy/dx"],
                    "keywords": ["dy/dx", "derivative"],
                },
                "tangents_normals": {
                    "methods": ["find the equation"],
                    "keywords": ["tangent", "normal", "gradient"],
                },
                "stationary_points": {
                    "methods": ["find", "determine"],
                    "keywords": ["stationary point", "maximum", "minimum"],
                },
            },
        },
        "integration": {
            "subtopics": {
                "standard": {
                    "methods": ["integrate"],
                    "keywords": ["integral", "constant of integration"],
                },
                "definite": {
                    "methods": ["evaluate", "integrate"],
                    "keywords": ["limits", "definite integral"],
                },
                "area_under_curve": {
                    "methods": ["find the area", "calculate the area"],
                    "keywords": ["area under the curve", "bounded by the curve"],
                },
            },
        },
        "numerical_methods": {
            "subtopics": {
                "change_of_sign": {
                    "methods": ["show", "verify"],
                    "keywords": ["root between", "change of sign"],
                },
                "iteration": {
                    "methods": ["use the iterative formula", "iterate"],
                    "keywords": ["x_(n+1)", "x_{n+1}", "recurrence relation"],
                },
            },
        },
    },

    "P2": {
        # Legacy / route-specific pure paper. Keep narrower than P3.
        "logarithmic_and_exponential_functions": {
            "subtopics": {
                "log_laws": {
                    "methods": ["simplify", "show that"],
                    "keywords": ["log", "ln"],
                },
                "equations": {
                    "methods": ["solve"],
                    "keywords": ["log", "ln", "e^", "exponential"],
                },
            },
        },
        "trigonometry": {
            "subtopics": {
                "equations": {"methods": ["solve"], "keywords": ["sin", "cos", "tan"]},
                "identities": {"methods": ["show that", "prove that"], "keywords": ["identity", "sec", "cosec", "cot"]},
            },
        },
        "differentiation": {
            "subtopics": {
                "stationary_points": {"methods": ["find"], "keywords": ["stationary point", "maximum", "minimum"]},
            },
        },
        "integration": {
            "subtopics": {
                "standard": {"methods": ["integrate"], "keywords": ["integral"]},
                "area_under_curve": {"methods": ["find the area"], "keywords": ["area under the curve"]},
            },
        },
    },

    "P3": {
        "logarithmic_and_exponential_functions": {
            "subtopics": {
                "log_laws": {"methods": ["simplify", "show that"], "keywords": ["log", "ln"]},
                "equations": {"methods": ["solve"], "keywords": ["log", "ln", "e^", "exponential"]},
            },
        },
        "trigonometry": {
            "subtopics": {
                "equations": {"methods": ["solve"], "keywords": ["sin", "cos", "tan", "sec", "cosec", "cot"]},
                "identities": {"methods": ["show that", "prove that"], "keywords": ["identity", "sec", "cosec", "cot"]},
            },
        },
        "integration": {
            "subtopics": {
                "by_parts": {
                    "methods": ["integrate", "use integration by parts"],
                    "keywords": ["by parts", "x e^", "x sin", "x cos", "x sec^2", "ln x"],
                },
                "by_substitution": {
                    "methods": ["integrate", "use the substitution"],
                    "keywords": ["substitution", "u =", "hence integrate"],
                },
                "partial_fractions": {
                    "methods": ["integrate"],
                    "keywords": ["partial fractions", "rational function"],
                },
                "recurrence": {
                    "methods": ["show that", "prove that"],
                    "keywords": ["I_n", "I_{n+1}", "reduction formula", "recurrence relation"],
                },
            },
        },
        "differentiation": {
            "subtopics": {
                "implicit": {
                    "methods": ["differentiate", "find dy/dx"],
                    "keywords": ["implicitly", "dy/dx"],
                },
                "parametric": {
                    "methods": ["find dy/dx", "find the equation of the tangent"],
                    "keywords": ["x =", "y =", "parameter", "dx/dt", "dy/dt"],
                },
            },
        },
        "parametric_equations": {
            "subtopics": {
                "area_or_length_style": {
                    "methods": ["find the area", "find the coordinates", "find the tangent"],
                    "keywords": ["parameter", "dx/dt", "dy/dt", "parametric"],
                },
            },
        },
        "differential_equations": {
            "subtopics": {
                "separable": {
                    "methods": ["solve", "separate variables"],
                    "keywords": ["dy/dx", "given that", "when x =", "when y ="],
                },
                "modelling": {
                    "methods": ["form", "solve"],
                    "keywords": ["rate of change", "differential equation"],
                },
            },
        },
        "vectors": {
            "subtopics": {
                "geometry": {
                    "methods": ["show that", "find", "determine"],
                    "keywords": ["position vector", "parallel", "perpendicular", "midpoint", "ratio"],
                },
                "vector_equations": {
                    "methods": ["find", "show that"],
                    "keywords": ["r =", "vector equation", "line", "scalar product"],
                },
            },
        },
        "complex_numbers": {
            "subtopics": {
                "argand": {
                    "methods": ["represent", "sketch"],
                    "keywords": ["argand", "complex plane"],
                },
                "modulus_argument": {
                    "methods": ["find", "calculate"],
                    "keywords": ["|z|", "arg z", "argument", "modulus"],
                },
                "roots": {
                    "methods": ["solve", "find the roots"],
                    "keywords": ["complex roots", "root of the equation", "z"],
                },
                "loci": {
                    "methods": ["describe", "sketch"],
                    "keywords": ["locus", "|z-a|", "arg"],
                },
            },
        },
        "series": {
            "subtopics": {
                "binomial_fractional_negative": {
                    "methods": ["expand", "approximate"],
                    "keywords": ["ascending powers", "valid for", "fractional power", "negative power"],
                },
                "maclaurin": {
                    "methods": ["expand", "obtain the first terms"],
                    "keywords": ["maclaurin", "series in ascending powers of x"],
                },
            },
        },
    },

    "P4": {
        "kinematics": {
            "subtopics": {
                "constant_acceleration": {
                    "methods": ["find", "calculate"],
                    "keywords": ["u", "v", "a", "s", "t", "constant acceleration"],
                },
                "variable_acceleration": {
                    "methods": ["differentiate", "integrate", "find"],
                    "keywords": ["displacement", "velocity", "acceleration", "particle"],
                },
            },
        },
        "forces_and_equilibrium": {
            "subtopics": {
                "resolving_forces": {
                    "methods": ["resolve", "find"],
                    "keywords": ["component", "inclined plane", "equilibrium"],
                },
                "friction": {
                    "methods": ["find", "calculate"],
                    "keywords": ["friction", "coefficient of friction", "limiting equilibrium", "about to move"],
                },
            },
        },
        "connected_particles": {
            "subtopics": {
                "tension_systems": {
                    "methods": ["find", "calculate"],
                    "keywords": ["connected particles", "string", "tension", "pulley"],
                },
            },
        },
        "momentum_and_impulse": {
            "subtopics": {
                "impulse": {
                    "methods": ["find", "calculate"],
                    "keywords": ["impulse", "momentum"],
                },
                "collisions": {
                    "methods": ["find", "calculate"],
                    "keywords": ["collision", "coefficient of restitution", "impact"],
                },
            },
        },
        "work_energy_power": {
            "subtopics": {
                "work_energy": {
                    "methods": ["find", "calculate", "use conservation of energy"],
                    "keywords": ["work", "kinetic energy", "potential energy", "loss in gravitational potential energy"],
                },
                "power": {
                    "methods": ["find", "calculate"],
                    "keywords": ["power", "rate of working"],
                },
            },
        },
        "circular_motion": {
            "subtopics": {
                "centripetal_force": {
                    "methods": ["find", "calculate"],
                    "keywords": ["circular motion", "centripetal", "speed at the lowest point", "tension"],
                },
            },
        },
    },

    "P5": {
        "permutations_and_combinations": {
            "subtopics": {
                "arrangements": {
                    "methods": ["find", "calculate"],
                    "keywords": ["arrangements", "different ways", "letters", "digits"],
                },
                "selections": {
                    "methods": ["find", "calculate"],
                    "keywords": ["committee", "choose", "selection"],
                },
            },
        },
        "probability": {
            "subtopics": {
                "basic": {"methods": ["find", "calculate"], "keywords": ["P(", "probability"]},
                "conditional": {"methods": ["find", "calculate"], "keywords": ["given that", "conditional probability"]},
                "tree_diagrams": {"methods": ["draw", "use"], "keywords": ["tree diagram", "branch"]},
            },
        },
        "discrete_random_variables": {
            "subtopics": {
                "expectation_variance": {
                    "methods": ["find", "calculate"],
                    "keywords": ["E(X)", "Var(X)", "random variable"],
                },
            },
        },
        "binomial_distribution": {
            "subtopics": {
                "direct": {"methods": ["find", "calculate"], "keywords": ["X ~ B", "Bin", "binomial distribution"]},
                "cumulative": {"methods": ["find", "calculate"], "keywords": ["at least", "at most", "more than", "fewer than"]},
            },
        },
        "poisson_distribution": {
            "subtopics": {
                "direct": {"methods": ["find", "calculate"], "keywords": ["Poisson", "X ~ Po", "mean rate"]},
            },
        },
        "normal_distribution": {
            "subtopics": {
                "standardisation": {
                    "methods": ["find", "calculate"],
                    "keywords": ["normal distribution", "standard deviation", "standardise", "z-value"],
                },
                "inverse": {
                    "methods": ["find"],
                    "keywords": ["percentage point", "find the value of k", "upper tail", "lower tail"],
                },
            },
        },
        "correlation_and_regression": {
            "subtopics": {
                "pmcc": {
                    "methods": ["calculate", "find"],
                    "keywords": ["product moment correlation coefficient", "PMCC"],
                },
                "regression": {
                    "methods": ["find", "estimate"],
                    "keywords": ["least squares regression line", "regression line of y on x"],
                },
                "interpretation": {
                    "methods": ["comment", "interpret"],
                    "keywords": ["correlation", "regression", "outlier"],
                },
            },
        },
    }
}

# Active classifier hints use the same family -> topic -> subtopic shape as
# DEFAULT_PAPER_FAMILY_TAXONOMY. CAIE_9709_HINTS above is kept as a broader
# note bank, but this is the structure consumed by classification.py.
CAIE_CLASSIFICATION_HINTS = {
    "P1": {
        "quadratics": {
            "solving": {"methods": ["solve", "factorise", "complete the square"], "objects": ["quadratic equation", "quadratic"], "keywords": ["discriminant", "roots"]},
            "discriminant": {"methods": ["find", "show"], "objects": ["discriminant"], "keywords": ["real roots", "equal roots"]},
        },
        "polynomials": {
            "factor_theorem": {"methods": ["factor theorem", "show"], "objects": ["polynomial"], "keywords": ["factor"]},
            "remainder_theorem": {"methods": ["remainder theorem", "find"], "objects": ["polynomial"], "keywords": ["remainder"]},
            "division": {"methods": ["divide"], "objects": ["polynomial"], "keywords": ["quotient"]},
        },
        "partial_fractions": {
            "decomposition": {"methods": ["partial fractions", "express.*partial fractions"], "objects": ["rational function", "proper fraction"], "keywords": ["denominator", "numerator"]},
        },
        "modulus": {
            "equations": {"methods": ["solve"], "objects": ["modulus"], "keywords": ["|x|", "absolute value"]},
            "inequalities": {"methods": ["solve"], "objects": ["modulus inequality"], "keywords": ["|x|", "<", ">"]},
            "graphs": {"methods": ["sketch"], "objects": ["modulus graph"], "keywords": ["|x|"]},
        },
        "functions": {
            "composite_functions": {"methods": ["find", "show"], "objects": ["composite function"], "keywords": ["fg", "gf", "f(g", "g(f"]},
            "inverse_functions": {"methods": ["find"], "objects": ["inverse function"], "keywords": ["inverse", "f^{-1}"]},
            "transformations": {"methods": ["sketch", "describe"], "objects": ["transformation"], "keywords": ["translation", "stretch", "reflection"]},
            "domain_range": {"methods": ["state", "find"], "objects": ["domain", "range"], "keywords": ["one-one"]},
        },
        "coordinate_geometry": {
            "straight_line": {"methods": ["find the equation", "show"], "objects": ["straight line", "gradient"], "keywords": ["perpendicular", "parallel"]},
            "circles": {"methods": ["find the equation", "show"], "objects": ["circle", "radius", "centre"], "keywords": ["diameter", "tangent"]},
        },
        "circular_measure": {
            "radians": {"methods": ["find", "calculate"], "objects": ["radian", "angle"], "keywords": ["theta"]},
            "arc_length_sector_area": {"methods": ["find", "calculate"], "objects": ["arc", "sector"], "keywords": ["arc length", "sector area"]},
        },
        "trigonometry": {
            "trig_equations": {"methods": ["solve"], "objects": ["trigonometric equation"], "keywords": ["sin", "cos", "tan"]},
            "trig_identities": {"methods": ["prove", "show"], "objects": ["identity"], "keywords": ["sin", "cos", "tan"]},
            "trig_graphs": {"methods": ["sketch", "draw"], "objects": ["trig graph"], "keywords": ["period", "amplitude"]},
        },
        "binomial_expansion": {
            "positive_integer": {"methods": ["expand"], "objects": ["binomial"], "keywords": ["ascending powers", "positive integer"]},
            "fractional_negative": {"methods": ["expand", "approximate"], "objects": ["negative power", "fractional power"], "keywords": ["ascending powers", "valid for"]},
            "approximation": {"methods": ["approximate", "estimate"], "objects": ["binomial expansion"], "keywords": ["valid for"]},
        },
        "differentiation": {
            "standard_differentiation": {"methods": ["differentiate", "find dy/dx"], "objects": ["derivative"], "keywords": ["gradient"]},
            "tangents_normals": {"methods": ["find the equation"], "objects": ["tangent", "normal"], "keywords": ["gradient"]},
            "stationary_points": {"methods": ["find", "determine"], "objects": ["stationary point"], "keywords": ["maximum", "minimum"]},
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
    "P2": {
        "logarithmic_and_exponential_functions": {
            "log_laws": {"methods": ["simplify", "show"], "objects": ["logarithm"], "keywords": ["log", "ln"]},
            "exponential_equations": {"methods": ["solve"], "objects": ["exponential equation"], "keywords": ["e^", "exp"]},
            "logarithmic_equations": {"methods": ["solve"], "objects": ["logarithmic equation"], "keywords": ["log", "ln"]},
        },
        "trigonometry": {
            "trig_equations": {"methods": ["solve"], "objects": ["trigonometric equation"], "keywords": ["sin", "cos", "tan"]},
            "trig_identities": {"methods": ["prove", "show"], "objects": ["identity"], "keywords": ["sin", "cos", "tan"]},
        },
        "differentiation": {
            "standard_differentiation": {"methods": ["differentiate", "find dy/dx"], "objects": ["derivative"], "keywords": ["gradient"]},
            "stationary_points": {"methods": ["find"], "objects": ["stationary point"], "keywords": ["maximum", "minimum"]},
        },
        "integration": {
            "standard_integration": {"methods": ["integrate"], "objects": ["integral"], "keywords": []},
            "area_under_curve": {"methods": ["find the area"], "objects": ["curve"], "keywords": ["area under"]},
        },
    },
    "P3": {
        "partial_fractions": {
            "decomposition": {"methods": ["partial fractions", "express.*partial fractions"], "objects": ["rational function"], "keywords": ["denominator", "numerator"]},
        },
        "logarithmic_and_exponential_functions": {
            "log_laws": {"methods": ["simplify", "show"], "objects": ["logarithm"], "keywords": ["log", "ln"]},
            "exponential_equations": {"methods": ["solve"], "objects": ["exponential equation"], "keywords": ["e^", "exp"]},
            "logarithmic_equations": {"methods": ["solve"], "objects": ["logarithmic equation"], "keywords": ["log", "ln"]},
        },
        "trigonometry": {
            "trig_substitutions": {"methods": ["substitution"], "objects": ["trigonometric"], "keywords": ["sec", "cosec", "cot"]},
            "trig_equations": {"methods": ["solve"], "objects": ["trigonometric equation"], "keywords": ["sin", "cos", "tan"]},
            "identities": {"methods": ["prove", "show"], "objects": ["identity"], "keywords": ["sec", "cosec", "cot"]},
        },
        "integration_by_parts": {
            "product_integrals": {"methods": ["integration by parts", "integrate"], "objects": ["x sec", "x sin", "x cos", "x e", "product requiring parts"], "keywords": ["sec^2", "ln"]},
        },
        "integration_by_substitution": {
            "substitution": {"methods": ["substitution", "using the substitution"], "objects": ["integral"], "keywords": ["u ="]},
        },
        "partial_fractions_integration": {
            "rational_integrals": {"methods": ["integrate"], "objects": ["partial fractions", "rational function"], "keywords": ["denominator"]},
        },
        "differential_equations": {
            "separable": {"methods": ["separate variables", "solve"], "objects": ["differential equation"], "keywords": ["dy/dx"]},
            "first_order_modelling": {"methods": ["model", "form", "solve"], "objects": ["differential equation"], "keywords": ["rate of change"]},
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
        "maclaurin_series": {
            "standard_series": {"methods": ["expand", "find"], "objects": ["maclaurin series"], "keywords": ["powers of x"]},
            "approximations": {"methods": ["approximate"], "objects": ["maclaurin series"], "keywords": ["powers of x"]},
        },
        "parametric_equations": {
            "differentiation": {"methods": ["differentiate", "find dy/dx"], "objects": ["parametric"], "keywords": ["dx/dt", "dy/dt"]},
            "integration": {"methods": ["integrate"], "objects": ["parametric"], "keywords": ["dx/dt"]},
        },
        "implicit_differentiation": {
            "implicit_curves": {"methods": ["differentiate", "find dy/dx"], "objects": ["implicit"], "keywords": ["implicitly"]},
        },
    },
    "P4": {
        "kinematics": {
            "constant_acceleration": {"methods": ["find", "calculate"], "objects": ["constant acceleration"], "keywords": ["suvat"]},
            "displacement_velocity_acceleration": {"methods": ["differentiate", "integrate", "find"], "objects": ["displacement", "velocity", "acceleration"], "keywords": ["particle"]},
            "velocity_time_graphs": {"methods": ["sketch", "find"], "objects": ["velocity-time graph"], "keywords": ["area under"]},
        },
        "forces_and_equilibrium": {
            "resolving_forces": {"methods": ["resolve", "find"], "objects": ["force"], "keywords": ["component"]},
            "friction": {"methods": ["find", "calculate"], "objects": ["friction"], "keywords": ["coefficient of friction"]},
            "limiting_equilibrium": {"methods": ["find", "calculate"], "objects": ["limiting equilibrium"], "keywords": ["about to move"]},
        },
        "connected_particles": {
            "strings": {"methods": ["find", "calculate"], "objects": ["connected particles", "string"], "keywords": ["tension", "pulley"]},
            "pulleys": {"methods": ["find", "calculate"], "objects": ["pulley"], "keywords": ["tension"]},
            "tension": {"methods": ["find", "calculate"], "objects": ["tension"], "keywords": ["string", "pulley"]},
        },
        "friction": {
            "coefficient_of_friction": {"methods": ["find", "calculate"], "objects": ["friction"], "keywords": ["coefficient of friction"]},
            "limiting_friction": {"methods": ["find"], "objects": ["limiting friction"], "keywords": ["about to move"]},
        },
        "momentum": {
            "impulse": {"methods": ["find", "calculate"], "objects": ["impulse"], "keywords": ["momentum"]},
            "collisions": {"methods": ["find", "calculate"], "objects": ["collision"], "keywords": ["coefficient of restitution"]},
        },
        "collisions": {
            "conservation_of_momentum": {"methods": ["find", "calculate"], "objects": ["collision"], "keywords": ["momentum"]},
            "coefficient_of_restitution": {"methods": ["find", "calculate"], "objects": ["coefficient of restitution"], "keywords": ["collision"]},
        },
        "work_energy_power": {
            "work": {"methods": ["find", "calculate"], "objects": ["work"], "keywords": ["force times distance"]},
            "kinetic_potential_energy": {"methods": ["find", "calculate"], "objects": ["kinetic energy", "potential energy"], "keywords": ["energy"]},
            "power": {"methods": ["find", "calculate"], "objects": ["power"], "keywords": ["rate of working"]},
        },
        "circular_motion": {
            "centripetal_force": {"methods": ["find", "calculate"], "objects": ["centripetal force"], "keywords": ["circular motion"]},
        },
        "variable_force": {
            "differential_equation_modelling": {"methods": ["form", "solve"], "objects": ["variable force", "differential equation"], "keywords": ["resistance"]},
        },
    },
    "P5": {
        "probability": {
            "basic_probability": {"methods": ["find", "calculate"], "objects": ["probability"], "keywords": ["P("]},
            "conditional_probability": {"methods": ["find", "calculate"], "objects": ["conditional probability"], "keywords": ["given that"]},
            "independent_events": {"methods": ["show", "find"], "objects": ["independent events"], "keywords": ["independent"]},
            "tree_diagrams": {"methods": ["draw", "use"], "objects": ["tree diagram"], "keywords": ["branch"]},
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
        "correlation_and_regression": {
            "product_moment_correlation": {"methods": ["find", "calculate"], "objects": ["correlation"], "keywords": ["product moment"]},
            "least_squares_regression": {"methods": ["find", "calculate"], "objects": ["regression line"], "keywords": ["least squares"]},
            "interpretation": {"methods": ["interpret", "comment"], "objects": ["correlation", "regression"], "keywords": ["context"]},
        },
    },
    "P6": {
        "continuous_random_variables": {
            "density_functions": {"methods": ["find", "show"], "objects": ["probability density function"], "keywords": ["density"]},
            "expectation_variance": {"methods": ["find", "calculate"], "objects": ["expectation", "variance"], "keywords": ["integral"]},
        },
        "confidence_intervals": {
            "population_mean": {"methods": ["find", "construct"], "objects": ["confidence interval"], "keywords": ["population mean"]},
        },
        "hypothesis_testing": {
            "binomial": {"methods": ["test"], "objects": ["binomial distribution"], "keywords": ["hypothesis", "significance"]},
            "poisson": {"methods": ["test"], "objects": ["poisson distribution"], "keywords": ["hypothesis", "significance"]},
            "normal": {"methods": ["test"], "objects": ["normal distribution"], "keywords": ["hypothesis", "significance"]},
        },
        "central_limit_theorem": {
            "approximation_using_clt": {"methods": ["approximate"], "objects": ["central limit theorem"], "keywords": ["large sample"]},
        },
    },
}

DEFAULT_TOPIC_TAXONOMY = _flatten_topic_taxonomy(DEFAULT_PAPER_FAMILY_TAXONOMY)
DEFAULT_CLASSIFICATION_HINTS = _deep_merge_dicts(
    _auto_classification_hints(DEFAULT_PAPER_FAMILY_TAXONOMY),
    CAIE_CLASSIFICATION_HINTS,
)
DEFAULT_TOPICS = list(DEFAULT_TOPIC_TAXONOMY)

DIFFICULTY_LABELS = ["easy", "average", "difficult"]

DEFAULT_DIFFICULTY_HEURISTICS = {
    "P1": {
        "routine_easy_topics": ["quadratics", "differentiation", "integration"],
        "difficult_topics": ["numerical_methods", "modulus", "binomial_expansion"],
        "linked_keywords": ["hence", "deduce", "using your answer"],
        "disguised_keywords": ["show that", "prove", "given that"],
    },
    "P2": {
        "routine_easy_topics": ["differentiation", "integration"],
        "difficult_topics": ["numerical_methods", "logarithmic_and_exponential_functions"],
        "linked_keywords": ["hence", "deduce", "using your answer"],
        "disguised_keywords": ["show that", "prove", "given that"],
    },
    "P3": {
        "routine_easy_topics": ["logarithmic_and_exponential_functions"],
        "difficult_topics": ["complex_numbers", "vectors", "differential_equations", "integration"],
        "linked_keywords": ["hence", "deduce", "using your answer"],
        "disguised_keywords": ["show that", "prove", "given that", "locus"],
    },
    "P4": {
        "routine_easy_topics": ["kinematics"],
        "difficult_topics": ["connected_particles", "forces_and_equilibrium", "momentum_and_impulse", "circular_motion"],
        "linked_keywords": ["hence", "therefore", "subsequently"],
        "disguised_keywords": ["model", "limiting", "coefficient of restitution"],
    },
    "P5": {
        "routine_easy_topics": [],
        "difficult_topics": ["probability", "correlation_and_regression"],
        "linked_keywords": ["given that", "conditional", "interpret"],
        "disguised_keywords": ["justify", "comment", "in context"],
    },
    "P6": {
        "routine_easy_topics": [],
        "difficult_topics": ["continuous_random_variables", "confidence_intervals", "hypothesis_testing", "central_limit_theorem"],
        "linked_keywords": ["given that", "conditional", "interpret"],
        "disguised_keywords": ["justify", "comment", "in context"],
    },
    "unknown": {
        "routine_easy_topics": [],
        "difficult_topics": [],
        "linked_keywords": ["hence", "deduce", "given that"],
        "disguised_keywords": ["show that", "prove"],
    },
}


@dataclass
class InputConfig:
    question_papers_dir: Path = Path("input/question_papers")
    mark_schemes_dir: Path = Path("input/mark_schemes")
    mappings_dir: Path = Path("input/mappings")
    examiner_reports_dir: Path = Path("input/examiner_reports")


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
    prompt_region_max_gap: float = 60
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
    include_mark_scheme_link: bool = True
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
    difficulty_heuristics: dict[str, dict[str, list[str]]] = field(
        default_factory=lambda: {family: {key: list(values) for key, values in data.items()} for family, data in DEFAULT_DIFFICULTY_HEURISTICS.items()}
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
        if family != "unknown" and (not isinstance(topics, dict) or not topics):
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

    merged_hints = _deep_merge_dicts(_auto_classification_hints(config.paper_family_taxonomy), config.classification_hints)
    valid_hints: dict[str, dict[str, dict[str, dict[str, list[str]]]]] = {}
    for family, topics in merged_hints.items():
        if family not in config.paper_family_taxonomy or not isinstance(topics, dict):
            continue
        for topic, subtopics in topics.items():
            if topic not in config.paper_family_taxonomy[family] or not isinstance(subtopics, dict):
                continue
            for subtopic, hints in subtopics.items():
                if subtopic not in config.paper_family_taxonomy[family][topic]:
                    continue
                _validate_hint_groups(hints, f"classification_hints.{family}.{topic}.{subtopic}")
                valid_hints.setdefault(family, {}).setdefault(topic, {})[subtopic] = hints
    config.classification_hints = valid_hints

    if config.difficulty_labels != DIFFICULTY_LABELS:
        raise ValueError(f"Difficulty labels must be exactly {DIFFICULTY_LABELS}.")
    if not isinstance(config.difficulty_heuristics, dict):
        raise ValueError("difficulty_heuristics must be a mapping.")
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
        elif key == "difficulty_heuristics":
            if not isinstance(value, dict):
                raise ValueError("Config section `difficulty_heuristics` must be a mapping.")
            config.difficulty_heuristics = _deep_merge_dicts(config.difficulty_heuristics, value)
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
