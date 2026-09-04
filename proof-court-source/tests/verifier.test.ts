import assert from 'node:assert/strict';
import test from 'node:test';

import { cases, objectionCategories, type ProofCase } from '../lib/cases.ts';
import { friendlyExplanation, validateEvidenceValue, verifyStructuredProof, type Submission } from '../lib/verifier.ts';

function validEvidence(caseFile: ProofCase) {
  if (caseFile.requiredEvidence !== undefined) return caseFile.requiredEvidence;
  if (caseFile.evidenceRange?.min !== undefined) return caseFile.evidenceRange.min;
  if (caseFile.evidenceKind === 'positive-natural') return 2;
  return 0;
}

function validSubmission(caseFile: ProofCase): Submission {
  return {
    selectedBlocks: [...caseFile.proofTemplate.solution],
    strategy: caseFile.allowedStrategies[0],
    auditLine: caseFile.proofTemplate.auditLine ?? null,
    objection: caseFile.proofTemplate.auditCategory ?? '',
    evidenceValue: validEvidence(caseFile),
    claimAnswers: Object.fromEntries((caseFile.claimQuestions ?? []).map((question) => [question.id, question.answer])),
    explanation: Object.fromEntries((caseFile.explanationFields ?? []).map((field) => [
      field.id,
      `We clearly use ${field.requiredConcepts.map((group) => group[0]).join(' and ')} in this sentence.`,
    ])),
  };
}

void test('every authored case has a valid, dependency-complete route', () => {
  for (const caseFile of cases) {
    const blockIds = new Set(caseFile.proofTemplate.blocks.map((block) => block.id));
    for (const solutionId of caseFile.proofTemplate.solution) assert.ok(blockIds.has(solutionId), `${caseFile.id}: missing solution block ${solutionId}`);
    for (const block of caseFile.proofTemplate.blocks) {
      for (const requirement of block.requires ?? []) assert.ok(blockIds.has(requirement), `${caseFile.id}: missing dependency ${requirement}`);
    }
    const result = verifyStructuredProof(caseFile, validSubmission(caseFile));
    assert.equal(result.accepted, true, `${caseFile.id}: ${result.heading} — ${result.message}`);
  }
});

void test('independent facts can be filed in either order, but conclusions cannot come first', () => {
  const caseFile = cases.find((item) => item.id === 'prime-testimony')!;
  const reversed = validSubmission(caseFile);
  reversed.selectedBlocks = ['p2', 'p1', 'p3'];
  assert.equal(verifyStructuredProof(caseFile, reversed).accepted, true);

  const premature = validSubmission(caseFile);
  premature.selectedBlocks = ['p3', 'p1', 'p2'];
  const result = verifyStructuredProof(caseFile, premature);
  assert.equal(result.accepted, false);
  assert.equal(result.objection, 'missing justification');
});

void test('audit cases enforce decisive evidence before accepting an objection', () => {
  const caseFile = cases.find((item) => item.id === 'audit-examples')!;
  const submission = validSubmission(caseFile);
  submission.evidenceValue = 39;
  const result = verifyStructuredProof(caseFile, submission);
  assert.equal(result.accepted, false);
  assert.equal(result.heading, 'The court needs a decisive witness');
});

void test('the selected proof strategy must match the authored route', () => {
  const caseFile = cases.find((item) => item.id === 'odd-square')!;
  const submission = validSubmission(caseFile);
  submission.strategy = 'Direct proof';
  assert.equal(verifyStructuredProof(caseFile, submission).accepted, false);
});

void test('a case may accept more than one genuinely matched proof route', () => {
  const caseFile = cases.find((item) => item.id === 'odd-square')!;
  const submission = validSubmission(caseFile);
  submission.strategy = 'Contradiction';
  submission.selectedBlocks = ['s5', 's6', 's7'];
  assert.equal(verifyStructuredProof(caseFile, submission).accepted, true);
});

void test('advanced explanations require mathematical concepts, not word count', () => {
  const caseFile = cases.find((item) => item.id === 'irrational-root')!;
  const submission = validSubmission(caseFile);
  submission.explanation = {
    assumption: 'blah blah blah blah blah blah blah blah',
    inference: 'blah blah blah blah blah blah blah blah',
    justification: 'blah blah blah blah blah blah blah blah',
    conclusion: 'blah blah blah blah blah blah blah blah',
  };
  const result = verifyStructuredProof(caseFile, submission);
  assert.equal(result.accepted, false);
  assert.equal(result.missingExplanationField, 'assumption');
});

void test('evidence validation enforces mathematical domains and ranges', () => {
  const integerCase = cases.find((item) => item.id === 'odd-witnesses')!;
  const naturalCase = cases.find((item) => item.id === 'audit-examples')!;
  const boundedCase = cases.find((item) => item.id === 'odd-sum-induction')!;
  assert.match(validateEvidenceValue(integerCase, 1.5) ?? '', /integers/i);
  assert.match(validateEvidenceValue(naturalCase, -1) ?? '', /natural/i);
  assert.match(validateEvidenceValue(boundedCase, 21) ?? '', /no greater than 20/i);
  assert.equal(validateEvidenceValue(integerCase, -3), null);
});

void test('every objection category has a specific student-facing explanation', () => {
  for (const category of objectionCategories) {
    const explanation = friendlyExplanation(category);
    assert.ok(explanation.length > 35, category);
  }
});
