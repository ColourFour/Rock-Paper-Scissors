import type { ExplanationField, ProofCase } from './cases';

export type Submission = {
  selectedBlocks: string[];
  strategy: string;
  auditLine: number | null;
  objection: string;
  evidenceValue: number | null;
  claimAnswers: Record<string, string>;
  explanation: Record<string, string>;
};

export type Verdict = {
  accepted: boolean;
  heading: string;
  message: string;
  objection?: string;
  problemStepId?: string;
  missingStepIds?: string[];
  missingExplanationField?: string;
  engine: 'structured-checker';
};

const engine = 'structured-checker' as const;

export function validateEvidenceValue(caseFile: ProofCase, value: number | null): string | null {
  if (caseFile.evidenceKind === 'none') return null;
  if (value === null || !Number.isFinite(value)) return 'Enter one valid number before continuing.';

  const kind = caseFile.evidenceKind ?? 'integer';
  if (kind === 'integer' && !Number.isInteger(value)) return 'This case is about integers. Enter a whole number such as −3, 0, or 4.';
  if (kind === 'natural' && (!Number.isInteger(value) || value < 0)) return 'This case is about natural numbers. Enter 0 or a positive whole number.';
  if (kind === 'positive-natural' && (!Number.isInteger(value) || value < 1)) return 'Enter a positive whole number: 1, 2, 3, and so on.';

  const { min, max } = caseFile.evidenceRange ?? {};
  if (min !== undefined && value < min) return `Enter a value of at least ${min} for this investigation.`;
  if (max !== undefined && value > max) return `Enter a value no greater than ${max} for this investigation.`;
  return null;
}

// Shared by the evidence screen and verdict checker so a valid witness opens
// the argument and is rechecked when the student submits their objection.
export function isEvidenceReady(caseFile: ProofCase, value: number | null): boolean {
  if (validateEvidenceValue(caseFile, value) !== null) return false;
  if (caseFile.requiredEvidence !== undefined && value !== caseFile.requiredEvidence) return false;
  if (caseFile.requiresCounterexample) return value !== null && caseFile.evidenceGenerator(value).counterexample;
  return true;
}

export function verifyStructuredProof(caseFile: ProofCase, submission: Submission): Verdict {
  const unanswered = (caseFile.claimQuestions ?? []).find((question) => submission.claimAnswers[question.id] !== question.answer);
  if (unanswered) {
    return {
      accepted: false,
      heading: 'Clarify the claim first',
      message: `Revisit “${unanswered.prompt}” A proof must start from the correct domain, hypothesis, conclusion, and quantifiers.`,
      objection: unanswered.id.includes('domain') ? 'missing domain' : 'quantifier error',
      engine,
    };
  }

  const evidenceError = validateEvidenceValue(caseFile, submission.evidenceValue);
  if (evidenceError) {
    return { accepted: false, heading: 'Evidence outside the case', message: evidenceError, objection: 'missing domain', engine };
  }

  if (!isEvidenceReady(caseFile, submission.evidenceValue)) {
    return {
      accepted: false,
      heading: 'The court needs a decisive witness',
      message: 'The value tested so far does not make the allegation fail. Keep searching for one counterexample in the stated domain.',
      objection: 'missing justification',
      engine,
    };
  }

  if (caseFile.proofTemplate.mode === 'audit') {
    const correctLine = caseFile.proofTemplate.auditLine;
    if (submission.auditLine !== correctLine) {
      const choseLaterLine = submission.auditLine !== null && correctLine !== undefined && submission.auditLine > correctLine;
      return {
        accepted: false,
        heading: 'Objection overruled',
        message: submission.auditLine === null
          ? 'Select the first line where validity breaks.'
          : choseLaterLine
            ? `Line ${submission.auditLine} may also fail, but it already depends on an earlier mistake. Object at the first unsupported line.`
            : `Line ${submission.auditLine} is supported by the statements before it. Keep reading for the first unsupported move.`,
        objection: 'unsupported inference',
        engine,
      };
    }
    if (submission.objection !== caseFile.proofTemplate.auditCategory) {
      return {
        accepted: false,
        heading: 'Correct line, sharper language needed',
        message: `You found the first faulty line. The precise objection is “${caseFile.proofTemplate.auditCategory}”: it ${friendlyExplanation(caseFile.proofTemplate.auditCategory ?? 'missing justification')}`,
        objection: caseFile.proofTemplate.auditCategory,
        engine,
      };
    }
    return {
      accepted: true,
      heading: 'Objection sustained',
      message: `Line ${submission.auditLine} is the first invalid step. Your objection names exactly why the inference fails.`,
      engine,
    };
  }

  if (!caseFile.allowedStrategies.includes(submission.strategy)) {
    return {
      accepted: false,
      heading: 'The method does not match this argument',
      message: `This route is built as ${caseFile.allowedStrategies.join(' or ')}. Choose a method whose assumptions and conclusion match the lines you file.`,
      objection: 'unsupported inference',
      engine,
    };
  }

  const chosen = submission.selectedBlocks;
  const route = caseFile.proofTemplate.routes?.find((candidate) => candidate.strategy === submission.strategy);
  const solution = route?.solution ?? caseFile.proofTemplate.solution;
  const openingLength = route?.opening.length ?? caseFile.proofTemplate.opening.length;
  const solutionSet = new Set(solution);
  const blocksById = new Map(caseFile.proofTemplate.blocks.map((block) => [block.id, block]));
  const objectionStepIndex = chosen.findIndex((id) => blocksById.get(id)?.objection);
  const objectionStep = objectionStepIndex >= 0 ? blocksById.get(chosen[objectionStepIndex]) : undefined;

  if (objectionStep?.objection) {
    return {
      accepted: false,
      heading: 'Objection',
      message: `Line ${openingLength + objectionStepIndex + 1} says “${objectionStep.text}” It ${friendlyExplanation(objectionStep.objection)}`,
      objection: objectionStep.objection,
      problemStepId: objectionStep.id,
      engine,
    };
  }

  const unsupportedId = chosen.find((id) => !solutionSet.has(id));
  if (unsupportedId) {
    const unsupported = blocksById.get(unsupportedId);
    return {
      accepted: false,
      heading: 'This line does not support the case',
      message: unsupported ? `“${unsupported.text}” is not part of a valid route from the facts to the verdict.` : 'This line is not recognized as part of this case.',
      objection: 'unsupported inference',
      problemStepId: unsupportedId,
      engine,
    };
  }

  const established = new Set<string>();
  for (const [index, id] of chosen.entries()) {
    const block = blocksById.get(id);
    if (!block) continue;
    const unmet = (block.requires ?? []).filter((requirement) => !established.has(requirement));
    if (unmet.length) {
      const requirements = unmet.map((requirement) => blocksById.get(requirement)?.text).filter(Boolean) as string[];
      return {
        accepted: false,
        heading: 'This conclusion comes too soon',
        message: `Line ${openingLength + index + 1} could be valid later, but it is not supported yet. First establish ${joinQuoted(requirements)}. Independent facts may appear in either order.`,
        objection: 'missing justification',
        problemStepId: id,
        missingStepIds: unmet,
        engine,
      };
    }
    established.add(id);
  }

  const missing = solution.filter((id) => !established.has(id));
  if (missing.length) {
    const missingTexts = missing.map((id) => blocksById.get(id)?.text).filter(Boolean) as string[];
    return {
      accepted: false,
      heading: 'Valid so far—one piece is missing',
      message: `Everything filed so far is supported. Complete the route by establishing ${joinQuoted(missingTexts)}.`,
      objection: 'missing justification',
      missingStepIds: missing,
      engine,
    };
  }

  const explanationProblem = findExplanationProblem(caseFile.explanationFields ?? [], submission.explanation);
  if (explanationProblem) {
    return {
      accepted: false,
      heading: 'The structure works—now explain the reasoning',
      message: explanationProblem.message,
      objection: 'missing justification',
      missingExplanationField: explanationProblem.field.id,
      engine,
    };
  }

  return {
    accepted: true,
    heading: 'Q.E.D. · Claim established',
    message: 'Every filed line follows from an admitted fact, definition, or justified inference. The structured judge accepts the argument.',
    engine,
  };
}

function findExplanationProblem(fields: ExplanationField[], explanation: Record<string, string>) {
  for (const field of fields) {
    const response = explanation[field.id]?.trim() ?? '';
    if (response.split(/\s+/).filter(Boolean).length < 4) {
      return { field, message: `Complete “${field.label}” in a full sentence. Use the frame “${field.sentenceFrame}” and name the mathematical idea.` };
    }
    const normalized = response.toLocaleLowerCase().replace(/\s+/g, ' ');
    const missingGroup = field.requiredConcepts.find((alternatives) => !alternatives.some((concept) => normalized.includes(concept.toLocaleLowerCase())));
    if (missingGroup) {
      return { field, message: `Your “${field.label}” sentence needs to identify ${missingGroup.join(' or ')}. Explain the mathematics, not just the verdict.` };
    }
  }
  return null;
}

function joinQuoted(items: string[]) {
  const quoted = items.map((item) => `“${item}”`);
  if (quoted.length <= 1) return quoted[0] ?? 'the missing fact';
  if (quoted.length === 2) return `${quoted[0]} and ${quoted[1]}`;
  return `${quoted.slice(0, -1).join(', ')}, and ${quoted.at(-1)}`;
}

export function friendlyExplanation(category: string) {
  const explanations: Record<string, string> = {
    'undefined term': 'uses a word or symbol whose mathematical meaning has not been stated.',
    'unsupported inference': 'does not follow from the facts currently established.',
    'converse error': 'uses a one-way conditional in the reverse direction.',
    'missing domain': 'does not say which values the variable is allowed to represent.',
    'example presented as proof': 'checks supporting examples but does not rule out an untested counterexample.',
    'quantifier error': 'changes the force of “every” or “there exists.”',
    'algebra error': 'changes the value of an expression during a rewrite.',
    'circular reasoning': 'assumes the same conclusion the argument is supposed to establish.',
    'missing justification': 'may be true, but no definition, theorem, or earlier fact has been given to support it.',
  };
  return explanations[category] ?? explanations['missing justification'];
}
