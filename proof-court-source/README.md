# Court of Proof

Court of Proof is a working classroom MVP for a four-week introductory proof unit. Students act as attorneys: they inspect claims, test evidence, assemble or write arguments, audit opposing counsel, and submit work to a judge.

## What is included

- Fourteen playable cases spanning predicates and truth sets, domains, quantifier negation, counterexamples, divisibility, direct proof, transfer, contrapositive, contradiction, induction, and proof audits.
- A calm, one-task-at-a-time flow: read the claim, test evidence, make the argument, then hear the verdict.
- An interactive first-case tutorial that highlights the current task and models the complete workflow before students work independently.
- A sequential campaign whose scaffolding fades from `guided` to `supported` to `independent`.
- An independence record stored in browser `localStorage`, tracking completed cases, attempts, claim-reading errors, hints, methods chosen, and submitted proof steps.
- Short plain-English renderings, claim-reading checks, consistent sentence frames, and a case-specific legal/math dictionary for ESL accessibility.
- A typed, reusable case schema and an explicit verification boundary.

## Architecture

- `app/page.tsx` owns the classroom experience and local student state.
- `lib/cases.ts` is the content layer. Every case is a `ProofCase` with its mathematical statement, domain, definitions, evidence generator, proof representation, Lean source, hints, errors, difficulty, stage, and case-board facts.
- `lib/verifier.ts` exposes the MVP verifier. It accepts a structured `Submission` and returns a stable, student-facing `Verdict`.
- `app/globals.css` defines the courtroom visual system and shared workspace patterns.

The browser sends only a structured proof object to the verifier. UI wording and formal verification are therefore decoupled:

`courtroom interaction → structured submission → verifier → judicial feedback`

## Authoring a case

Add one `ProofCase` object to `cases` in `lib/cases.ts`.

1. Write both `claim` (symbolic) and `plainEnglish`.
2. State the `domain`, legal definitions, strategy list, campaign stage, and difficulty.
3. Set `evidenceKind`, optional `evidenceRange`, and an `evidenceGenerator`. Inputs are validated against the mathematical domain before the generator runs.
4. Choose a `proofTemplate.mode`: `blocks`, `fill-gap`, `strategy`, or `audit`.
5. For proof-building cases, author the required block IDs under `solution`. Order in this list is not enforced.
6. Add `requires` to any block that depends on earlier facts. The verifier accepts every ordering that respects these dependencies, so independent facts can be presented in either order.
7. For audit cases, set the first invalid `auditLine` and exact `auditCategory`.
8. Add `claimQuestions` that assess the domain, quantifiers, hypothesis, conclusion, or equivalent form rather than merely displaying them.
9. Set `scaffoldLevel` to control whether dependency and justification cues appear.
10. For advanced cases, add four `explanationFields`: assumption, inference, justification, and conclusion. Each field lists the mathematical concepts required in the response.
11. Include the intended `leanTheorem` and `leanProof`, even though this MVP does not execute them.

## Verification: honest MVP status

Lean 4 is **not running in this deployment**. The introduction, header, and every verdict clearly label results as coming from the “Structured proof checker · Lean theorem prepared, not executed.” The fallback checker validates:

- claim interpretation and chosen proof method;
- evidence domain and any required decisive counterexample;
- presence of required proof steps and their logical dependencies;
- proof-audit line and objection category;
- four-part student explanations against case-specific mathematical concepts in advanced cases.

It maps failures to classroom categories such as unsupported inference, converse error, example presented as proof, and missing justification. Raw checker details are never shown to students.

## Connecting Lean 4 next

Keep `verifyStructuredProof(caseFile, submission)` as the client contract and replace its implementation with a server-side verifier adapter.

1. Convert the structured block IDs and student inputs to the case’s authored Lean theorem and proof template.
2. Run Lean in an isolated service with Mathlib pinned to a known version and strict time/resource limits.
3. Return a small result type: accepted, error location, and a stable machine-readable category.
4. Translate Lean elaboration errors in the service. Never return raw Lean output to the student.
5. Mark the UI as “Lean verified” only when that service actually returns success.

Do not send arbitrary student text directly to a shell or Lean process. Generate Lean from the structured representation and allowlisted case templates.

## Campaign and teacher preview

Student progress starts empty. Completing a case unlocks the next case. “Mathematical independence” means a case was accepted on the first filing without a claim-reading error or structural hint.

For curriculum review, append `?preview=1` to the page URL to unlock every case. Preview mode is visibly labeled and is not intended for student assessment.

Progress is intentionally local for the MVP. It is device- and browser-specific, contains no student identity, and is validated before loading. A classroom backend would be required for durable teacher reporting.

## Quality checks

- `npm test` runs structured-verifier regression tests, including domain validation, flexible ordering, method matching, audit evidence, and advanced explanations.
- `npm run lint` checks the authored app, content, static entry point, and tests.
- `npm run build` creates the production application build.
- `npm run build:edgeone` creates the static bundle used for static hosting.

The public GitHub Pages repository should receive the output of `npm run build:edgeone`; do not edit generated assets by hand. The publishing repository copies that committed static bundle into its Pages artifact.

## Local development

Use the scripts in `package.json`: `npm run dev` for the live classroom preview and `npm run build` for a production build.
