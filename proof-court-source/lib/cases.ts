export type CampaignStage =
  | 'Junior Associate'
  | 'Counsel'
  | 'Trial Attorney'
  | 'Senior Counsel'
  | 'Supreme Court';

export type ProofMode = 'blocks' | 'fill-gap' | 'strategy' | 'audit';
export type EvidenceKind = 'integer' | 'natural' | 'positive-natural' | 'real' | 'none';
export type ScaffoldLevel = 'guided' | 'supported' | 'independent';

export type ClaimQuestion = {
  id: string;
  prompt: string;
  options: string[];
  answer: string;
  explanation: string;
};

export type ExplanationField = {
  id: 'assumption' | 'inference' | 'justification' | 'conclusion';
  label: string;
  sentenceFrame: string;
  requiredConcepts: string[][];
};

export type ProofBlock = {
  id: string;
  text: string;
  support: string;
  requires?: string[];
  objection?: string;
};

export type ProofRoute = {
  strategy: string;
  opening: string[];
  solution: string[];
};

export type ProofCase = {
  id: string;
  title: string;
  subtitle: string;
  claim: string;
  plainEnglish: string;
  domain: string;
  definitions: { term: string; meaning: string }[];
  allowedStrategies: string[];
  strategyOptions?: string[];
  claimQuestions?: ClaimQuestion[];
  evidenceKind?: EvidenceKind;
  evidencePrompt?: string;
  evidenceRange?: { min?: number; max?: number };
  scaffoldLevel?: ScaffoldLevel;
  explanationFields?: ExplanationField[];
  evidenceGenerator: (value: number) => { result: string; counterexample: boolean };
  proofTemplate: {
    mode: ProofMode;
    instruction: string;
    opening: string[];
    blocks: ProofBlock[];
    solution: string[];
    routes?: ProofRoute[];
    auditLine?: number;
    auditCategory?: string;
  };
  leanTheorem: string;
  leanProof: string;
  hints: string[];
  commonErrors: string[];
  difficulty: number;
  campaignStage: CampaignStage;
  facts: { label: string; value: string; detail: string; state: 'given' | 'derived' | 'goal' }[];
  lesson: string;
  requiredEvidence?: number;
};

const divides = (a: number, b: number) => b % a === 0;

const coreCases: ProofCase[] = [
  {
    id: 'prime-testimony',
    title: 'Prime Testimony',
    subtitle: 'A decisive counterexample',
    claim: '∀ p ∈ ℕ, Prime(p) → Odd(p)',
    plainEnglish: 'Every prime number is odd.',
    domain: 'Natural numbers ℕ',
    definitions: [
      { term: 'Prime', meaning: 'A whole number greater than 1 with exactly two positive divisors.' },
      { term: 'Counterexample', meaning: 'One example that makes a universal claim false.' },
    ],
    allowedStrategies: ['Counterexample search'],
    strategyOptions: ['Counterexample search', 'Direct proof'],
    evidenceKind: 'natural',
    evidencePrompt: 'Enter a natural number that could defeat the claim.',
    scaffoldLevel: 'guided',
    claimQuestions: [{
      id: 'claim-kind',
      prompt: 'What kind of claim is this?',
      options: ['Universal: it says every prime', 'Existential: it says some prime', 'A definition of prime'],
      answer: 'Universal: it says every prime',
      explanation: 'The word “every” makes this a universal claim. One counterexample can defeat it.',
    }],
    evidenceGenerator: (p) => ({
      result: p === 2 ? '2 is prime and 2 is not odd. This is decisive evidence.' : `${p} does not settle the entire claim. Try a prime that might break it.`,
      counterexample: p === 2,
    }),
    proofTemplate: {
      mode: 'blocks',
      instruction: 'Find the witness that defeats the universal claim, then file your conclusion.',
      opening: ['The allegation says every prime must be odd.'],
      blocks: [
        { id: 'p1', text: '2 is prime because its only positive divisors are 1 and 2.', support: 'Definition of prime' },
        { id: 'p2', text: '2 is even, so it is not odd.', support: 'Definition of even and odd' },
        { id: 'p3', text: 'Therefore, 2 is a counterexample and the claim is false.', support: 'Universal claims need only one counterexample', requires: ['p1', 'p2'] },
        { id: 'p4', text: '3, 5, and 7 are odd, so every prime is odd.', support: 'Checked examples', objection: 'example presented as proof' },
      ],
      solution: ['p1', 'p2', 'p3'],
    },
    leanTheorem: 'example : ¬ (∀ p : ℕ, Nat.Prime p → Odd p) := by',
    leanProof: '  push_neg\n  exact ⟨2, Nat.prime_two, by decide⟩',
    hints: ['A universal claim falls if one valid case fails.', 'Test the smallest prime number.'],
    commonErrors: ['example presented as proof', 'quantifier error'],
    difficulty: 1,
    campaignStage: 'Junior Associate',
    facts: [
      { label: 'Allegation', value: 'Every prime is odd', detail: 'Universal claim', state: 'given' },
      { label: 'Witness', value: 'p = ?', detail: 'Find one prime that is not odd', state: 'derived' },
      { label: 'Verdict sought', value: 'Claim is false', detail: 'File a counterexample', state: 'goal' },
    ],
    lesson: 'One counterexample disproves a universal statement.',
    requiredEvidence: 2,
  },
  {
    id: 'divisibility-brief',
    title: 'The Divisibility Brief',
    subtitle: 'Definitions carry the case',
    claim: '∀ n ∈ ℤ, 4 ∣ n → 2 ∣ n',
    plainEnglish: 'For every integer n, if 4 divides n, then 2 divides n.',
    domain: 'Integers ℤ',
    definitions: [{ term: 'a divides b', meaning: 'There is an integer k such that b = ak.' }],
    allowedStrategies: ['Direct proof'],
    strategyOptions: ['Direct proof', 'Contrapositive', 'Counterexample search'],
    evidenceKind: 'integer',
    evidencePrompt: 'Test an integer. Values divisible by 4 are the useful witnesses.',
    scaffoldLevel: 'guided',
    claimQuestions: [
      { id: 'hypothesis', prompt: 'Which fact may we assume?', options: ['4 divides n', '2 divides n', 'n is positive'], answer: '4 divides n', explanation: 'The hypothesis is the statement after “if.”' },
      { id: 'conclusion', prompt: 'Which verdict must we reach?', options: ['4 divides n', '2 divides n', 'n is even and positive'], answer: '2 divides n', explanation: 'The conclusion is the statement after “then.”' },
      { id: 'negation', prompt: 'Which sentence correctly negates the claim?', options: ['There exists an integer n with 4 ∣ n and 2 ∤ n.', 'Every integer divisible by 2 is divisible by 4.', 'There exists an integer n with 4 ∤ n and 2 ∣ n.'], answer: 'There exists an integer n with 4 ∣ n and 2 ∤ n.', explanation: 'To negate “for every, P → Q,” assert that one case has P true and Q false.' },
    ],
    evidenceGenerator: (n) => ({ result: divides(4, n) ? `${n} = 4(${n / 4}), and 2 also divides ${n}. Evidence supports the claim.` : `The hypothesis fails for ${n}, so this value cannot test the conclusion.`, counterexample: false }),
    proofTemplate: {
      mode: 'blocks',
      instruction: 'Arrange the supported lines. One tempting line is inadmissible.',
      opening: ['Let n be an integer.', 'Assume 4 divides n.'],
      blocks: [
        { id: 'd1', text: 'By definition, n = 4k for some integer k.', support: 'Definition of divisibility' },
        { id: 'd2', text: 'Rewrite n = 2(2k). Since 2k is an integer, 2 divides n.', support: 'Algebra and definition of divisibility', requires: ['d1'] },
        { id: 'd3', text: 'Therefore, if 4 divides n, then 2 divides n.', support: 'Direct proof complete', requires: ['d2'] },
        { id: 'd4', text: '4, 8, and 12 work, so the claim is proved.', support: 'Examples', objection: 'example presented as proof' },
      ],
      solution: ['d1', 'd2', 'd3'],
    },
    leanTheorem: 'theorem four_dvd_implies_two_dvd (n : ℤ) (h : 4 ∣ n) : 2 ∣ n := by',
    leanProof: '  obtain ⟨k, rfl⟩ := h\n  exact ⟨2 * k, by ring⟩',
    hints: ['Open the definition of 4 ∣ n.', 'Write 4k as 2 times an integer.'],
    commonErrors: ['example presented as proof', 'missing justification'],
    difficulty: 1,
    campaignStage: 'Junior Associate',
    facts: [
      { label: 'Fact of the case', value: '4 ∣ n', detail: 'Hypothesis', state: 'given' },
      { label: 'By definition', value: 'n = 4k', detail: 'for some integer k', state: 'derived' },
      { label: 'Verdict sought', value: '2 ∣ n', detail: 'Conclusion', state: 'goal' },
    ],
    lesson: 'A direct proof starts from the hypothesis and uses definitions to reach the conclusion.',
  },
  {
    id: 'odd-witnesses',
    title: 'Two Odd Witnesses',
    subtitle: 'A scaffolded direct proof',
    claim: '∀ a b ∈ ℤ, Odd(a) ∧ Odd(b) → Even(a + b)',
    plainEnglish: 'The sum of two odd integers is even.',
    domain: 'Integers ℤ',
    definitions: [
      { term: 'Odd integer', meaning: 'An integer of the form 2k + 1.' },
      { term: 'Even integer', meaning: 'An integer of the form 2k.' },
    ],
    allowedStrategies: ['Direct proof'],
    strategyOptions: ['Direct proof', 'Contrapositive', 'Contradiction'],
    evidenceKind: 'integer',
    evidencePrompt: 'Enter one odd integer. The lab will pair it with 3.',
    scaffoldLevel: 'supported',
    claimQuestions: [{ id: 'definition', prompt: 'What should a direct proof do first?', options: ['Write both odd integers using 2k + 1', 'Check several odd pairs', 'Assume the sum is even'], answer: 'Write both odd integers using 2k + 1', explanation: 'Definitions turn the two hypotheses into algebra that applies to every pair.' }],
    evidenceGenerator: (a) => ({ result: Math.abs(a % 2) === 1 ? `${a} and 3 are odd. Their sum is ${a + 3}, which is even. This is evidence, not the general proof.` : `${a} is even, so it does not match the hypothesis. Choose an odd integer.`, counterexample: false }),
    proofTemplate: {
      mode: 'fill-gap',
      instruction: 'Supply the missing bridge from the definitions to the verdict.',
      opening: ['Let a and b be integers.', 'Assume a and b are odd.'],
      blocks: [
        { id: 'o1', text: 'By definition, a = 2m + 1 and b = 2k + 1 for integers m and k.', support: 'Definition of odd' },
        { id: 'o2', text: 'Then a + b = 2m + 1 + 2k + 1 = 2(m + k + 1).', support: 'Algebra', requires: ['o1'] },
        { id: 'o3', text: 'Since m + k + 1 is an integer, a + b is even.', support: 'Definition of even', requires: ['o2'] },
        { id: 'o4', text: 'Odd plus odd looks even in the evidence lab.', support: 'Examples', objection: 'example presented as proof' },
      ],
      solution: ['o1', 'o2', 'o3'],
    },
    leanTheorem: 'theorem odd_add_odd_even (a b : ℤ) (ha : Odd a) (hb : Odd b) : Even (a + b) := by',
    leanProof: '  obtain ⟨m, rfl⟩ := ha\n  obtain ⟨k, rfl⟩ := hb\n  exact ⟨m + k + 1, by ring⟩',
    hints: ['Translate both uses of “odd” into equations.', 'Factor 2 from the sum.'],
    commonErrors: ['algebra error', 'missing justification'],
    difficulty: 2,
    campaignStage: 'Counsel',
    facts: [
      { label: 'Facts', value: 'a, b are odd', detail: 'Hypothesis', state: 'given' },
      { label: 'Definitions', value: 'a=2m+1, b=2k+1', detail: 'Introduce witnesses', state: 'derived' },
      { label: 'Verdict sought', value: 'a + b is even', detail: 'Conclusion', state: 'goal' },
    ],
    lesson: 'Definitions turn words into algebra you can use.',
  },
  {
    id: 'odd-square',
    title: 'The Odd Square',
    subtitle: 'Choose the contrapositive',
    claim: '∀ n ∈ ℤ, Odd(n²) → Odd(n)',
    plainEnglish: 'If the square of an integer is odd, then the integer is odd.',
    domain: 'Integers ℤ',
    definitions: [
      { term: 'Contrapositive', meaning: 'To prove P → Q, prove not Q → not P.' },
      { term: 'Inverse', meaning: 'The statement not P → not Q. It is not automatically equivalent to P → Q.' },
    ],
    allowedStrategies: ['Contrapositive', 'Contradiction'],
    strategyOptions: ['Direct proof', 'Contrapositive', 'Contradiction'],
    evidenceKind: 'integer',
    evidencePrompt: 'Test an integer and compare its parity with the parity of its square.',
    scaffoldLevel: 'supported',
    claimQuestions: [
      { id: 'contrapositive', prompt: 'Which equivalent claim is the contrapositive?', options: ['If n is even, then n² is even.', 'If n is odd, then n² is odd.', 'If n² is even, then n is even.'], answer: 'If n is even, then n² is even.', explanation: 'The contrapositive of “n² odd → n odd” is “n even → n² even.”' },
      { id: 'inverse', prompt: 'Which statement is the inverse?', options: ['If n² is not odd, then n is not odd.', 'If n is even, then n² is even.', 'If n is odd, then n² is odd.'], answer: 'If n² is not odd, then n is not odd.', explanation: 'The inverse negates both parts without reversing them: not P → not Q.' },
    ],
    evidenceGenerator: (n) => ({ result: `${n}² = ${n * n}. Both ${n} and ${n * n} are ${Math.abs(n % 2) === 1 ? 'odd' : 'even'}.`, counterexample: false }),
    proofTemplate: {
      mode: 'strategy',
      instruction: 'Choose a method, then build the cleanest argument.',
      opening: ['We prove the contrapositive.', 'Let n be an integer and assume n is even.'],
      blocks: [
        { id: 's1', text: 'By definition, n = 2k for some integer k.', support: 'Definition of even' },
        { id: 's2', text: 'Then n² = (2k)² = 2(2k²), so n² is even.', support: 'Algebra and definition of even', requires: ['s1'] },
        { id: 's3', text: 'Therefore, by contrapositive, if n² is odd, then n is odd.', support: 'Logical equivalence', requires: ['s2'] },
        { id: 's5', text: 'If n were not odd, then n would be even, so n = 2k for some integer k.', support: 'Integer parity and definition of even' },
        { id: 's6', text: 'Then n² = 2(2k²), which is even.', support: 'Algebra and definition of even', requires: ['s5'] },
        { id: 's7', text: 'This contradicts the assumption that n² is odd. Therefore n is odd.', support: 'Contradiction', requires: ['s6'] },
        { id: 's4', text: 'If n² is odd, divide both sides by n to see n is odd.', support: 'Unsupported operation', objection: 'unsupported inference' },
      ],
      solution: ['s1', 's2', 's3'],
      routes: [
        { strategy: 'Contrapositive', opening: ['We prove the contrapositive.', 'Let n be an integer and assume n is even.'], solution: ['s1', 's2', 's3'] },
        { strategy: 'Contradiction', opening: ['Let n be an integer and assume n² is odd.', 'Assume for contradiction that n is not odd.'], solution: ['s5', 's6', 's7'] },
      ],
    },
    leanTheorem: 'theorem odd_of_sq_odd (n : ℤ) (h : Odd (n^2)) : Odd n := by',
    leanProof: '  contrapose! h\n  exact Int.even_sq.mpr h',
    hints: ['Turn the conclusion “n is odd” into the assumption “n is even.”', 'The square of 2k has a factor of 2.'],
    commonErrors: ['converse error', 'unsupported inference'],
    difficulty: 3,
    campaignStage: 'Trial Attorney',
    facts: [
      { label: 'Original claim', value: 'n² odd → n odd', detail: 'Conditional', state: 'given' },
      { label: 'Contrapositive', value: 'n even → n² even', detail: 'Equivalent claim', state: 'derived' },
      { label: 'Verdict sought', value: 'Original is true', detail: 'By contrapositive', state: 'goal' },
    ],
    lesson: 'The contrapositive is logically equivalent and can be easier to prove.',
  },
  {
    id: 'irrational-root',
    title: 'The Irrational Witness',
    subtitle: 'A contradiction in lowest terms',
    claim: 'Irrational(√2)',
    plainEnglish: 'The square root of 2 is irrational.',
    domain: 'Real numbers ℝ',
    definitions: [{ term: 'Irrational', meaning: 'A real number that cannot be written as a ratio of integers.' }, { term: 'Lowest terms', meaning: 'Numerator and denominator share no factor greater than 1.' }],
    allowedStrategies: ['Contradiction'],
    strategyOptions: ['Direct proof', 'Contradiction', 'Mathematical induction'],
    evidenceKind: 'positive-natural',
    evidencePrompt: 'Choose 2–8 decimal places to inspect. Decimal evidence cannot settle irrationality.',
    evidenceRange: { min: 2, max: 8 },
    scaffoldLevel: 'independent',
    claimQuestions: [{ id: 'opposite', prompt: 'What do we assume for contradiction?', options: ['√2 = a/b in lowest terms', '√2 has infinitely many digits', 'a and b are both even'], answer: '√2 = a/b in lowest terms', explanation: 'The negation of irrationality is that √2 is a ratio of integers; choose that ratio in lowest terms.' }],
    explanationFields: [
      { id: 'assumption', label: 'Assumption', sentenceFrame: 'Assume for contradiction that…', requiredConcepts: [['assume'], ['sqrt', '√2'], ['rational', 'a/b', 'ratio']] },
      { id: 'inference', label: 'Key inference', sentenceFrame: 'The equations force…', requiredConcepts: [['even'], ['a'], ['b']] },
      { id: 'justification', label: 'Why that is impossible', sentenceFrame: 'This contradicts…', requiredConcepts: [['contradict'], ['lowest', 'common factor']] },
      { id: 'conclusion', label: 'Verdict', sentenceFrame: 'Therefore…', requiredConcepts: [['irrational'], ['sqrt', '√2']] },
    ],
    evidenceGenerator: (n) => ({ result: `A decimal such as ${Math.sqrt(2).toFixed(Math.min(8, Math.max(2, Math.abs(n))))} can suggest a pattern, but decimals cannot prove irrationality.`, counterexample: false }),
    proofTemplate: {
      mode: 'strategy',
      instruction: 'Assume the opposite and expose the contradiction.',
      opening: ['Assume for contradiction that √2 = a/b, where a/b is in lowest terms.'],
      blocks: [
        { id: 'r1', text: 'Squaring gives a² = 2b², so a² is even and therefore a is even.', support: 'Algebra and parity precedent' },
        { id: 'r2', text: 'Write a = 2k. Substitution gives b² = 2k², so b is even.', support: 'Substitution and parity precedent', requires: ['r1'] },
        { id: 'r3', text: 'Then a and b share a factor of 2, contradicting that a/b was in lowest terms.', support: 'Contradiction', requires: ['r1', 'r2'] },
        { id: 'r4', text: 'The decimal digits do not repeat, so √2 is irrational.', support: 'Observed decimals', objection: 'unsupported inference' },
      ],
      solution: ['r1', 'r2', 'r3'],
    },
    leanTheorem: 'theorem sqrt_two_irrational : Irrational (Real.sqrt 2) := by',
    leanProof: '  exact irrational_sqrt_two',
    hints: ['Assume √2 has a fraction in lowest terms.', 'Show both numerator and denominator must be even.'],
    commonErrors: ['circular reasoning', 'missing justification'],
    difficulty: 4,
    campaignStage: 'Senior Counsel',
    facts: [
      { label: 'Opposite assumed', value: '√2 = a/b', detail: 'a/b in lowest terms', state: 'given' },
      { label: 'Consequences', value: 'a even and b even', detail: 'Shared factor 2', state: 'derived' },
      { label: 'Contradiction', value: 'Not lowest terms', detail: 'Original assumption fails', state: 'goal' },
    ],
    lesson: 'Contradiction proves a claim by showing its negation is impossible.',
  },
  {
    id: 'odd-sum-induction',
    title: 'The Chain of Precedent',
    subtitle: 'Induction carries the ruling',
    claim: '∀ n ∈ ℕ, 1 + 3 + ⋯ + (2n − 1) = n²',
    plainEnglish: 'The sum of the first n odd positive integers equals n squared.',
    domain: 'Natural numbers ℕ, n ≥ 1',
    definitions: [{ term: 'Base case', meaning: 'Establish the first precedent.' }, { term: 'Inductive step', meaning: 'Show that truth at k forces truth at k + 1.' }],
    allowedStrategies: ['Mathematical induction'],
    strategyOptions: ['Check examples', 'Direct proof', 'Mathematical induction'],
    evidenceKind: 'positive-natural',
    evidencePrompt: 'Enter a natural number from 1 to 20.',
    evidenceRange: { min: 1, max: 20 },
    scaffoldLevel: 'independent',
    claimQuestions: [{ id: 'method', prompt: 'Why is induction suitable?', options: ['The statement is indexed by every natural number', 'The formula was checked three times', 'The conclusion is a conditional'], answer: 'The statement is indexed by every natural number', explanation: 'Induction establishes a first case and a step that reaches every later natural number.' }],
    explanationFields: [
      { id: 'assumption', label: 'Precedent', sentenceFrame: 'First establish… Then assume…', requiredConcepts: [['base', 'n = 1'], ['assume', 'hypothesis'], ['k']] },
      { id: 'inference', label: 'Propagation', sentenceFrame: 'For k + 1, add…', requiredConcepts: [['2k + 1', 'next odd'], ['k²', 'k^2'], ['(k + 1)²', '(k+1)^2']] },
      { id: 'justification', label: 'Authority', sentenceFrame: 'This is justified by…', requiredConcepts: [['inductive hypothesis'], ['algebra']] },
      { id: 'conclusion', label: 'Verdict', sentenceFrame: 'Therefore…', requiredConcepts: [['every', 'all'], ['n'], ['n²', 'n^2']] },
    ],
    evidenceGenerator: (n) => { const x = Math.max(1, Math.min(20, Math.abs(Math.trunc(n)))); return { result: `For n = ${x}, the odd-number sum is ${x * x}, and n² is ${x * x}. This is evidence, not the general proof.`, counterexample: false }; },
    proofTemplate: {
      mode: 'strategy',
      instruction: 'Establish precedent, assume it at k, then show it propagates.',
      opening: ['Base case n = 1: the sum is 1 = 1².', 'Assume the claim holds for n = k.'],
      blocks: [
        { id: 'i1', text: 'The next sum is [1 + 3 + ⋯ + (2k − 1)] + (2k + 1).', support: 'Add the next odd term' },
        { id: 'i2', text: 'By the inductive hypothesis, this equals k² + 2k + 1 = (k + 1)².', support: 'Inductive hypothesis and algebra', requires: ['i1'] },
        { id: 'i3', text: 'Therefore the claim holds for k + 1, so it holds for every n ≥ 1.', support: 'Principle of induction', requires: ['i2'] },
        { id: 'i4', text: 'The formula works for n = 1, 2, and 3, so it holds for all n.', support: 'Checked examples', objection: 'example presented as proof' },
      ],
      solution: ['i1', 'i2', 'i3'],
    },
    leanTheorem: 'theorem sum_first_odd (n : ℕ) : ∑ i in Finset.range n, (2*i + 1) = n^2 := by',
    leanProof: '  induction n with\n  | zero => simp\n  | succ n ih => simp [Finset.sum_range_succ, ih]; ring',
    hints: ['The next odd number after 2k − 1 is 2k + 1.', 'Use the inductive hypothesis before simplifying.'],
    commonErrors: ['example presented as proof', 'missing justification'],
    difficulty: 5,
    campaignStage: 'Supreme Court',
    facts: [
      { label: 'Precedent', value: 'n = 1', detail: 'Base case', state: 'given' },
      { label: 'Assumed ruling', value: 'Sₖ = k²', detail: 'Inductive hypothesis', state: 'derived' },
      { label: 'Propagation', value: 'Sₖ₊₁ = (k+1)²', detail: 'Inductive step', state: 'goal' },
    ],
    lesson: 'Induction proves an infinite chain by establishing a start and a reliable next step.',
  },
  {
    id: 'audit-examples',
    title: 'The Pattern Trap',
    subtitle: 'Opposing counsel audit',
    claim: '∀ n ∈ ℕ, n² + n + 41 is prime',
    plainEnglish: 'For every natural number n, n squared plus n plus 41 is prime.',
    domain: 'Natural numbers ℕ',
    definitions: [
      { term: 'Proof audit', meaning: 'Identify the exact unsupported line and name the objection.' },
      { term: 'Conjecture', meaning: 'A mathematical allegation suggested by evidence but not yet proved.' },
    ],
    allowedStrategies: ['Object to opposing counsel'],
    evidenceKind: 'natural',
    evidencePrompt: 'Search for a natural number that breaks the pattern.',
    scaffoldLevel: 'independent',
    claimQuestions: [
      { id: 'status', prompt: 'After checking only n = 0, 1, 2, 3, and 4, what do we have?', options: ['A conjecture supported by evidence', 'A completed universal proof', 'A mathematical definition'], answer: 'A conjecture supported by evidence', explanation: 'A pattern can motivate a conjecture, but checked cases do not prove it.' },
      { id: 'quantifier', prompt: 'What would defeat this universal claim?', options: ['One natural number with a composite output', 'Five natural numbers with prime outputs', 'A new formula with the same first values'], answer: 'One natural number with a composite output', explanation: 'One failed case disproves a universal claim.' },
    ],
    evidenceGenerator: (n) => { const v = n * n + n + 41; return { result: `At n = ${n}, the expression is ${v}. ${n === 40 ? 'This equals 41 × 41, so it is not prime.' : 'One result cannot settle a universal claim.'}`, counterexample: n === 40 }; },
    proofTemplate: {
      mode: 'audit',
      instruction: 'Select the first faulty line and the exact objection category.',
      opening: ['Line 1. I checked n = 0, 1, 2, 3, and 4.', 'Line 2. The outputs 41, 43, 47, 53, and 61 are all prime.', 'Line 3. Therefore n² + n + 41 is prime for every natural number n.'],
      blocks: [],
      solution: [],
      auditLine: 3,
      auditCategory: 'example presented as proof',
    },
    leanTheorem: 'example : ¬ (∀ n : ℕ, Nat.Prime (n^2 + n + 41)) := by',
    leanProof: '  push_neg\n  refine ⟨40, ?_⟩\n  norm_num [Nat.prime_def]',
    hints: ['Which line changes from “some” cases to “every” case?', 'Checked examples are investigation, not a universal proof.'],
    commonErrors: ['example presented as proof', 'quantifier error'],
    difficulty: 3,
    campaignStage: 'Trial Attorney',
    facts: [
      { label: 'Evidence checked', value: 'n = 0, 1, 2, 3, 4', detail: 'Five examples', state: 'given' },
      { label: 'Unsupported leap', value: 'Some → every', detail: 'Audit the quantifier', state: 'derived' },
      { label: 'Your duty', value: 'Object precisely', detail: 'Line + category', state: 'goal' },
    ],
    lesson: 'Many confirming examples still do not prove a universal statement.',
    requiredEvidence: 40,
  },
  {
    id: 'audit-converse',
    title: 'The Reversed Testimony',
    subtitle: 'Opposing counsel audit',
    claim: 'If a figure is a square, then it is a rectangle.',
    plainEnglish: 'Every square is a rectangle.',
    domain: 'Plane figures',
    definitions: [{ term: 'Converse error', meaning: 'Using P → Q as if Q → P were also true.' }],
    allowedStrategies: ['Object to opposing counsel'],
    evidenceKind: 'positive-natural',
    evidencePrompt: 'Choose a positive side length for a non-square rectangle.',
    scaffoldLevel: 'independent',
    claimQuestions: [{ id: 'direction', prompt: 'Which direction is actually established?', options: ['square → rectangle', 'rectangle → square', 'square ↔ rectangle'], answer: 'square → rectangle', explanation: 'A true conditional does not automatically establish its converse.' }],
    evidenceGenerator: (n) => ({ result: `A ${n} by ${n + 1} rectangle is a rectangle but not a square. The converse fails.`, counterexample: true }),
    proofTemplate: {
      mode: 'audit',
      instruction: 'The original claim is true, but opposing counsel’s argument is invalid. Find the first bad line.',
      opening: ['Line 1. Every square is a rectangle.', 'Line 2. Figure F is a rectangle.', 'Line 3. Therefore figure F is a square.'],
      blocks: [],
      solution: [],
      auditLine: 3,
      auditCategory: 'converse error',
    },
    leanTheorem: 'theorem square_is_rectangle (F : Figure) (h : IsSquare F) : IsRectangle F := by',
    leanProof: '  exact h.isRectangle',
    hints: ['Name the hypothesis and conclusion in line 1.', 'Line 3 tries to travel through the conditional backward.'],
    commonErrors: ['converse error', 'unsupported inference'],
    difficulty: 3,
    campaignStage: 'Trial Attorney',
    facts: [
      { label: 'Valid precedent', value: 'Square → rectangle', detail: 'One direction only', state: 'given' },
      { label: 'New fact', value: 'F is a rectangle', detail: 'Conclusion is known', state: 'derived' },
      { label: 'Questioned verdict', value: 'F is a square', detail: 'Does not follow', state: 'goal' },
    ],
    lesson: 'A conditional does not automatically prove its converse.',
  },
];

const supplementalCases: ProofCase[] = [
  {
    id: 'truth-set-hearing',
    title: 'The Truth Set Hearing',
    subtitle: 'A predicate needs a domain',
    claim: '{n ∈ ℤ | n² < 10} = {−3, −2, −1, 0, 1, 2, 3}',
    plainEnglish: 'The integers whose squares are less than 10 are exactly −3 through 3.',
    domain: 'Integers ℤ',
    definitions: [
      { term: 'Predicate', meaning: 'A sentence with a variable that becomes true or false when the variable is chosen.' },
      { term: 'Truth set', meaning: 'Every value in the domain that makes a predicate true.' },
    ],
    allowedStrategies: ['Direct calculation'],
    strategyOptions: ['Direct calculation', 'Mathematical induction', 'Check one example'],
    evidenceKind: 'integer',
    evidencePrompt: 'Test an integer and decide whether it belongs to the truth set.',
    scaffoldLevel: 'guided',
    claimQuestions: [
      { id: 'domain', prompt: 'What values are allowed?', options: ['Integers', 'Real numbers', 'Positive integers only'], answer: 'Integers', explanation: 'The symbol ℤ fixes the domain as all integers.' },
      { id: 'predicate', prompt: 'Which predicate decides membership?', options: ['n² < 10', 'n < 10', 'n² = 10'], answer: 'n² < 10', explanation: 'A number belongs exactly when its square is less than 10.' },
    ],
    evidenceGenerator: (n) => ({ result: `${n}² = ${n * n}, so ${n} ${n * n < 10 ? 'belongs' : 'does not belong'} to the truth set.`, counterexample: false }),
    proofTemplate: {
      mode: 'blocks',
      instruction: 'Use the domain and inequality to identify every possible integer.',
      opening: ['Let n be an integer and consider the predicate n² < 10.'],
      blocks: [
        { id: 't1', text: 'If n² < 10, then −√10 < n < √10.', support: 'Square-root bounds' },
        { id: 't2', text: 'The integers between those bounds are −3, −2, −1, 0, 1, 2, and 3.', support: 'Integer domain', requires: ['t1'] },
        { id: 't3', text: 'Each listed integer has square less than 10, so the list is exactly the truth set.', support: 'Check both directions', requires: ['t2'] },
        { id: 't4', text: 'The number 0 works, so the truth set is proved.', support: 'One example', objection: 'example presented as proof' },
      ],
      solution: ['t1', 't2', 't3'],
    },
    leanTheorem: 'example (n : ℤ) : n^2 < 10 ↔ n = -3 ∨ n = -2 ∨ n = -1 ∨ n = 0 ∨ n = 1 ∨ n = 2 ∨ n = 3 := by',
    leanProof: '  omega',
    hints: ['The domain is integers, not all real numbers.', 'Find the integers strictly between −√10 and √10.'],
    commonErrors: ['missing domain', 'example presented as proof'],
    difficulty: 1,
    campaignStage: 'Junior Associate',
    facts: [
      { label: 'Domain', value: 'n ∈ ℤ', detail: 'Only integers are eligible', state: 'given' },
      { label: 'Predicate', value: 'n² < 10', detail: 'Membership test', state: 'derived' },
      { label: 'Truth set', value: '{−3,…,3}', detail: 'All and only solutions', state: 'goal' },
    ],
    lesson: 'A predicate has meaning only after its domain is fixed.',
  },
  {
    id: 'negation-witness',
    title: 'The Negation Warrant',
    subtitle: 'Translate “not every” precisely',
    claim: '∀ n ∈ ℤ, n² ≥ 1',
    plainEnglish: 'Every integer has a square at least 1.',
    domain: 'Integers ℤ',
    definitions: [{ term: 'Negation', meaning: 'A statement that is true exactly when the original statement is false.' }],
    allowedStrategies: ['Counterexample search'],
    strategyOptions: ['Counterexample search', 'Direct proof', 'Mathematical induction'],
    evidenceKind: 'integer',
    evidencePrompt: 'Find an integer whose square is less than 1.',
    scaffoldLevel: 'guided',
    claimQuestions: [{ id: 'negation', prompt: 'What is the exact negation?', options: ['There exists an integer n with n² < 1.', 'Every integer n has n² < 1.', 'There exists an integer n with n² ≥ 1.'], answer: 'There exists an integer n with n² < 1.', explanation: '“Not every” becomes “there exists,” and ≥ becomes <.' }],
    evidenceGenerator: (n) => ({ result: `${n}² = ${n * n}. ${n === 0 ? 'This is less than 1, so the universal claim fails.' : 'This value does not defeat the claim.'}`, counterexample: n === 0 }),
    proofTemplate: {
      mode: 'blocks',
      instruction: 'Present one integer that satisfies the negation.',
      opening: ['The negation asks for an integer n with n² < 1.'],
      blocks: [
        { id: 'n1', text: 'Choose n = 0, which is an integer.', support: 'Domain and witness' },
        { id: 'n2', text: 'Then n² = 0² = 0, and 0 < 1.', support: 'Calculation', requires: ['n1'] },
        { id: 'n3', text: 'Therefore n = 0 is a counterexample, so the claim is false.', support: 'Negation of a universal claim', requires: ['n2'] },
        { id: 'n4', text: 'The claim sounds true for most integers, so it is true.', support: 'Informal impression', objection: 'missing justification' },
      ],
      solution: ['n1', 'n2', 'n3'],
    },
    leanTheorem: 'example : ¬ (∀ n : ℤ, n^2 ≥ 1) := by',
    leanProof: '  push_neg\n  exact ⟨0, by norm_num⟩',
    hints: ['“Not every” means “there exists one that fails.”', 'Test zero.'],
    commonErrors: ['quantifier error', 'missing domain'],
    difficulty: 1,
    campaignStage: 'Junior Associate',
    facts: [
      { label: 'Allegation', value: '∀n, n² ≥ 1', detail: 'Universal claim', state: 'given' },
      { label: 'Negation', value: '∃n, n² < 1', detail: 'Witness needed', state: 'derived' },
      { label: 'Verdict sought', value: 'Claim is false', detail: 'Produce n = 0', state: 'goal' },
    ],
    lesson: 'Negating a universal statement produces one existential counterexample.',
    requiredEvidence: 0,
  },
  {
    id: 'multiple-six-transfer',
    title: 'The Six-Factor Transfer',
    subtitle: 'Use the same structure with new numbers',
    claim: '∀ n ∈ ℤ, 6 ∣ n → 3 ∣ n',
    plainEnglish: 'Every integer divisible by 6 is also divisible by 3.',
    domain: 'Integers ℤ',
    definitions: [{ term: 'a divides b', meaning: 'There is an integer k such that b = ak.' }],
    allowedStrategies: ['Direct proof'],
    strategyOptions: ['Direct proof', 'Check examples', 'Mathematical induction'],
    evidenceKind: 'integer',
    evidencePrompt: 'Test an integer divisible by 6, then build a proof for every such integer.',
    scaffoldLevel: 'supported',
    claimQuestions: [{ id: 'start', prompt: 'How should the proof begin?', options: ['Assume n = 6k for some integer k', 'Assume n = 3', 'Check n = 6, 12, and 18'], answer: 'Assume n = 6k for some integer k', explanation: 'Open the divisibility hypothesis using its definition.' }],
    evidenceGenerator: (n) => ({ result: divides(6, n) ? `${n} = 6(${n / 6}) = 3(${2 * (n / 6)}). The example supports the claim.` : `${n} is not divisible by 6, so the hypothesis does not apply.`, counterexample: false }),
    proofTemplate: {
      mode: 'fill-gap',
      instruction: 'Transfer the divisibility argument without copying its exact numbers.',
      opening: ['Let n be an integer.', 'Assume 6 divides n.'],
      blocks: [
        { id: 'm1', text: 'By definition, n = 6k for some integer k.', support: 'Definition of divisibility' },
        { id: 'm2', text: 'Rewrite n = 3(2k), and 2k is an integer.', support: 'Algebra and closure', requires: ['m1'] },
        { id: 'm3', text: 'Therefore 3 divides n.', support: 'Definition of divisibility', requires: ['m2'] },
        { id: 'm4', text: 'Because 6 is bigger than 3, 3 divides n.', support: 'Size comparison', objection: 'unsupported inference' },
      ],
      solution: ['m1', 'm2', 'm3'],
    },
    leanTheorem: 'theorem six_dvd_implies_three_dvd (n : ℤ) (h : 6 ∣ n) : 3 ∣ n := by',
    leanProof: '  obtain ⟨k, rfl⟩ := h\n  exact ⟨2 * k, by ring⟩',
    hints: ['Use the definition of 6 ∣ n.', 'Write 6k as 3 times an integer.'],
    commonErrors: ['unsupported inference', 'example presented as proof'],
    difficulty: 2,
    campaignStage: 'Counsel',
    facts: [
      { label: 'Fact', value: '6 ∣ n', detail: 'n = 6k', state: 'given' },
      { label: 'Bridge', value: '6k = 3(2k)', detail: '2k is an integer', state: 'derived' },
      { label: 'Verdict', value: '3 ∣ n', detail: 'Definition reached', state: 'goal' },
    ],
    lesson: 'Transfer means recognizing a proof structure when the surface details change.',
  },
  {
    id: 'audit-algebra',
    title: 'The Missing Two',
    subtitle: 'Opposing counsel changes the value',
    claim: 'The sum of two odd integers is even.',
    plainEnglish: 'Adding any two odd integers produces an even integer.',
    domain: 'Integers ℤ',
    definitions: [{ term: 'Algebra error', meaning: 'A rewrite that does not preserve the value of an expression.' }],
    allowedStrategies: ['Object to opposing counsel'],
    evidenceKind: 'integer',
    evidencePrompt: 'Test an odd integer; the lab pairs it with 5.',
    scaffoldLevel: 'supported',
    claimQuestions: [{ id: 'audit-goal', prompt: 'What must an audit identify?', options: ['The first invalid line and why it fails', 'Any line that looks difficult', 'Only the final conclusion'], answer: 'The first invalid line and why it fails', explanation: 'Later lines may depend on the first error, so object where validity first breaks.' }],
    evidenceGenerator: (n) => ({ result: n % 2 === 0 ? `${n} is even; choose an odd integer to match the hypothesis.` : `${n} + 5 = ${n + 5}, an even number. This is supporting evidence only.`, counterexample: false }),
    proofTemplate: {
      mode: 'audit',
      instruction: 'Find the first rewrite that changes the expression.',
      opening: ['Line 1. Let a = 2m + 1 and b = 2k + 1.', 'Line 2. Then a + b = 2m + 2k + 1.', 'Line 3. Therefore a + b is even.'],
      blocks: [], solution: [], auditLine: 2, auditCategory: 'algebra error',
    },
    leanTheorem: 'theorem odd_add_odd_even_audit (a b : ℤ) (ha : Odd a) (hb : Odd b) : Even (a + b) := by',
    leanProof: '  exact ha.add hb',
    hints: ['Add both constant terms carefully.', 'The two copies of +1 add to 2, not 1.'],
    commonErrors: ['algebra error'], difficulty: 3, campaignStage: 'Trial Attorney',
    facts: [
      { label: 'Definitions', value: '2m+1 and 2k+1', detail: 'Both odd', state: 'given' },
      { label: 'Disputed rewrite', value: 'Constants: 1+1', detail: 'Check the algebra', state: 'derived' },
      { label: 'Your duty', value: 'Object at first error', detail: 'Name the category', state: 'goal' },
    ],
    lesson: 'A valid proof requires every algebraic rewrite to preserve equality.',
  },
  {
    id: 'audit-circular',
    title: 'The Borrowed Verdict',
    subtitle: 'Opposing counsel assumes the goal',
    claim: 'If n is even, then n² is even.',
    plainEnglish: 'The square of every even integer is even.',
    domain: 'Integers ℤ',
    definitions: [{ term: 'Circular reasoning', meaning: 'Using the conclusion as a reason for itself.' }],
    allowedStrategies: ['Object to opposing counsel'],
    evidenceKind: 'integer',
    evidencePrompt: 'Test an even integer and compare evidence with a general proof.',
    scaffoldLevel: 'independent',
    claimQuestions: [{ id: 'goal', prompt: 'What is the verdict sought?', options: ['n² is even', 'n is even', 'n² is positive'], answer: 'n² is even', explanation: 'The conclusion after “then” is what the proof must establish without assuming it.' }],
    evidenceGenerator: (n) => ({ result: n % 2 === 0 ? `${n}² = ${n * n}, which is even. This supports but does not prove the universal claim.` : `${n} is odd, so it does not satisfy the hypothesis.`, counterexample: false }),
    proofTemplate: {
      mode: 'audit',
      instruction: 'Find where counsel quietly assumes the verdict sought.',
      opening: ['Line 1. Let n be an even integer.', 'Line 2. Since n² is even, write n² = 2k.', 'Line 3. Therefore n² is even.'],
      blocks: [], solution: [], auditLine: 2, auditCategory: 'circular reasoning',
    },
    leanTheorem: 'theorem even_square_audit (n : ℤ) (h : Even n) : Even (n^2) := by',
    leanProof: '  exact h.pow_two',
    hints: ['Which line first mentions the conclusion as if it were known?', 'A proof may use the hypothesis, but it may not borrow the verdict.'],
    commonErrors: ['circular reasoning'], difficulty: 4, campaignStage: 'Senior Counsel',
    facts: [
      { label: 'Fact', value: 'n is even', detail: 'Allowed assumption', state: 'given' },
      { label: 'Verdict sought', value: 'n² is even', detail: 'Not yet established', state: 'derived' },
      { label: 'Audit', value: 'Find borrowed verdict', detail: 'Circular reasoning', state: 'goal' },
    ],
    lesson: 'A conclusion cannot serve as its own justification.',
  },
  {
    id: 'sum-induction-transfer',
    title: 'The Sum Statute',
    subtitle: 'Construct a second induction argument',
    claim: '∀ n ≥ 1, 1 + 2 + ⋯ + n = n(n + 1)/2',
    plainEnglish: 'The sum of the first n positive integers is n times n plus 1, divided by 2.',
    domain: 'Natural numbers ℕ, n ≥ 1',
    definitions: [{ term: 'Inductive hypothesis', meaning: 'The statement assumed at k while proving the next case.' }],
    allowedStrategies: ['Mathematical induction'],
    strategyOptions: ['Check examples', 'Contradiction', 'Mathematical induction'],
    evidenceKind: 'positive-natural',
    evidencePrompt: 'Enter a natural number from 1 to 30.',
    evidenceRange: { min: 1, max: 30 },
    scaffoldLevel: 'independent',
    claimQuestions: [{ id: 'next-term', prompt: 'What term is added to move from k to k + 1?', options: ['k + 1', '2k + 1', 'k²'], answer: 'k + 1', explanation: 'The next partial sum adds the next positive integer.' }],
    evidenceGenerator: (n) => ({ result: `For n = ${n}, both the sum and formula equal ${(n * (n + 1)) / 2}. This is evidence, not proof.`, counterexample: false }),
    proofTemplate: {
      mode: 'strategy',
      instruction: 'Reuse the induction structure with a new formula and less guidance.',
      opening: ['Base case n = 1: 1 = 1(2)/2.', 'Assume 1 + 2 + ⋯ + k = k(k + 1)/2.'],
      blocks: [
        { id: 'u1', text: 'For k + 1, the sum is k(k + 1)/2 + (k + 1).', support: 'Add the next term and use the hypothesis' },
        { id: 'u2', text: 'Factor to obtain (k + 1)(k + 2)/2.', support: 'Algebra', requires: ['u1'] },
        { id: 'u3', text: 'This is the required formula at k + 1, so induction proves the claim.', support: 'Principle of induction', requires: ['u2'] },
        { id: 'u4', text: 'The formula works at n = 10, so it works for every n.', support: 'One example', objection: 'example presented as proof' },
      ], solution: ['u1', 'u2', 'u3'],
    },
    explanationFields: [
      { id: 'assumption', label: 'Precedent', sentenceFrame: 'Establish the base case and assume…', requiredConcepts: [['base', 'n = 1'], ['assume', 'hypothesis'], ['k']] },
      { id: 'inference', label: 'Propagation', sentenceFrame: 'At k + 1…', requiredConcepts: [['k + 1'], ['add', 'next term'], ['factor']] },
      { id: 'justification', label: 'Authority', sentenceFrame: 'This follows from…', requiredConcepts: [['inductive hypothesis'], ['algebra']] },
      { id: 'conclusion', label: 'Verdict', sentenceFrame: 'Therefore…', requiredConcepts: [['induction'], ['every', 'all'], ['natural']] },
    ],
    leanTheorem: 'theorem sum_first_n (n : ℕ) : 2 * (∑ i in Finset.range (n + 1), i) = n * (n + 1) := by',
    leanProof: '  induction n with\n  | zero => simp\n  | succ n ih => simp [Finset.sum_range_succ, ih]; omega',
    hints: ['Add k + 1 to the formula at k.', 'Factor out k + 1 before comparing with the target.'],
    commonErrors: ['example presented as proof', 'algebra error'], difficulty: 5, campaignStage: 'Supreme Court',
    facts: [
      { label: 'Base', value: 'n = 1', detail: 'First case', state: 'given' },
      { label: 'Hypothesis', value: 'Sₖ = k(k+1)/2', detail: 'Assumed at k', state: 'derived' },
      { label: 'Step', value: 'Sₖ₊₁ = (k+1)(k+2)/2', detail: 'Prove next case', state: 'goal' },
    ],
    lesson: 'Transfer is demonstrated when the induction structure survives a change of formula.',
  },
];

const caseSequence = [
  'prime-testimony',
  'truth-set-hearing',
  'negation-witness',
  'divisibility-brief',
  'odd-witnesses',
  'multiple-six-transfer',
  'odd-square',
  'audit-examples',
  'audit-converse',
  'audit-algebra',
  'irrational-root',
  'audit-circular',
  'odd-sum-induction',
  'sum-induction-transfer',
];

export const cases: ProofCase[] = [...coreCases, ...supplementalCases].sort(
  (a, b) => caseSequence.indexOf(a.id) - caseSequence.indexOf(b.id),
);

export const objectionCategories = [
  'undefined term',
  'unsupported inference',
  'converse error',
  'missing domain',
  'example presented as proof',
  'quantifier error',
  'algebra error',
  'circular reasoning',
  'missing justification',
];

export const stages: CampaignStage[] = [
  'Junior Associate',
  'Counsel',
  'Trial Attorney',
  'Senior Counsel',
  'Supreme Court',
];
