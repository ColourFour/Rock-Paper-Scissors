'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  ChevronRight,
  CircleHelp,
  FileSearch,
  FlaskConical,
  Gavel,
  Link as LinkIcon,
  List,
  Lock,
  RotateCcw,
  Scale,
  ShieldCheck,
  X,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { cases, objectionCategories, type ProofCase } from '@/lib/cases';
import { validateEvidenceValue, verifyStructuredProof, type Verdict } from '@/lib/verifier';

type ProgressState = {
  version: 2;
  completed: string[];
  attemptsByCase: Record<string, number>;
  hintsByCase: Record<string, number>;
  claimErrorsByCase: Record<string, number>;
  stepsFiledByCase: Record<string, number>;
  methodsChosen: Record<string, string>;
};

const emptyProgress: ProgressState = {
  version: 2,
  completed: [],
  attemptsByCase: {},
  hintsByCase: {},
  claimErrorsByCase: {},
  stepsFiledByCase: {},
  methodsChosen: {},
};

const storageKey = 'court-of-proof-progress-v2';
const phaseLabels = ['Read the claim', 'Test evidence', 'Make your case', 'Hear the verdict'];

function parseProgress(raw: string | null): ProgressState {
  if (!raw) return emptyProgress;
  try {
    const value = JSON.parse(raw) as Partial<ProgressState> | null;
    if (!value || value.version !== 2 || !Array.isArray(value.completed)) return emptyProgress;
    const validIds = new Set(cases.map((caseFile) => caseFile.id));
    const record = (candidate: unknown) => {
      if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) return {};
      return Object.fromEntries(Object.entries(candidate).filter(([id, count]) => validIds.has(id) && typeof count === 'number' && Number.isFinite(count) && count >= 0));
    };
    const strings = (candidate: unknown) => {
      if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) return {};
      return Object.fromEntries(Object.entries(candidate).filter(([id, value]) => validIds.has(id) && typeof value === 'string'));
    };
    return {
      version: 2,
      completed: value.completed.filter((id): id is string => typeof id === 'string' && validIds.has(id)),
      attemptsByCase: record(value.attemptsByCase),
      hintsByCase: record(value.hintsByCase),
      claimErrorsByCase: record(value.claimErrorsByCase),
      stepsFiledByCase: record(value.stepsFiledByCase),
      methodsChosen: strings(value.methodsChosen),
    };
  } catch {
    return emptyProgress;
  }
}

export default function Home() {
  const [showIntro, setShowIntro] = useState(true);
  const [tutorialActive, setTutorialActive] = useState(true);
  const [phase, setPhase] = useState(0);
  const [caseIndex, setCaseIndex] = useState(0);
  const [plainEnglish, setPlainEnglish] = useState(true);
  const [claimAnswers, setClaimAnswers] = useState<Record<string, string>>({});
  const [selectedBlocks, setSelectedBlocks] = useState<string[]>([]);
  const [strategy, setStrategy] = useState('');
  const [evidenceInput, setEvidenceInput] = useState('');
  const [evidenceValue, setEvidenceValue] = useState<number | null>(null);
  const [evidenceResult, setEvidenceResult] = useState('');
  const [auditLine, setAuditLine] = useState<number | null>(null);
  const [objection, setObjection] = useState('');
  const [explanation, setExplanation] = useState<Record<string, string>>({});
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [hintIndex, setHintIndex] = useState(-1);
  const [dictionaryOpen, setDictionaryOpen] = useState(false);
  const [docketOpen, setDocketOpen] = useState(false);
  const [progress, setProgress] = useState<ProgressState>(() => typeof window === 'undefined' ? emptyProgress : parseProgress(window.localStorage.getItem(storageKey)));
  const [previewMode] = useState(() => typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('preview') === '1');

  const caseFile = cases[caseIndex];
  const scaffoldLevel = caseFile.scaffoldLevel ?? (caseFile.difficulty <= 1 ? 'guided' : caseFile.difficulty <= 3 ? 'supported' : 'independent');

  useEffect(() => {
    window.localStorage.setItem(storageKey, JSON.stringify(progress));
  }, [progress]);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setDictionaryOpen(false);
      setDocketOpen(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, []);

  const independence = useMemo(() => {
    if (!progress.completed.length) return 0;
    const independent = progress.completed.filter((id) =>
      !progress.hintsByCase[id]
      && !progress.claimErrorsByCase[id]
      && progress.attemptsByCase[id] === 1,
    ).length;
    return Math.round((independent / progress.completed.length) * 100);
  }, [progress]);

  const chosenBlocks = selectedBlocks
    .map((id) => caseFile.proofTemplate.blocks.find((block) => block.id === id))
    .filter(Boolean);

  function isUnlocked(index: number) {
    return previewMode || index === 0 || progress.completed.includes(cases[index - 1].id);
  }

  function openCase(nextIndex: number, tutorial = false) {
    if (!isUnlocked(nextIndex)) return;
    setCaseIndex(nextIndex);
    setPhase(0);
    setTutorialActive(tutorial);
    setPlainEnglish(true);
    setClaimAnswers({});
    setSelectedBlocks([]);
    setStrategy((cases[nextIndex].strategyOptions?.length ?? 0) > 1 ? '' : cases[nextIndex].allowedStrategies[0] ?? '');
    setEvidenceInput('');
    setEvidenceValue(null);
    setEvidenceResult('');
    setAuditLine(null);
    setObjection('');
    setExplanation({});
    setVerdict(null);
    setHintIndex(-1);
    setDocketOpen(false);
  }

  function answerClaim(questionId: string, answer: string) {
    const question = caseFile.claimQuestions?.find((item) => item.id === questionId);
    setClaimAnswers((current) => ({ ...current, [questionId]: answer }));
    if (question && answer !== question.answer && claimAnswers[questionId] !== answer) {
      setProgress((current) => ({
        ...current,
        claimErrorsByCase: { ...current.claimErrorsByCase, [caseFile.id]: (current.claimErrorsByCase[caseFile.id] ?? 0) + 1 },
      }));
    }
  }

  function testEvidence() {
    const value = Number(evidenceInput);
    const error = validateEvidenceValue(caseFile, Number.isFinite(value) ? value : null);
    if (error) {
      setEvidenceValue(null);
      setEvidenceResult(error);
      return;
    }
    setEvidenceValue(value);
    setEvidenceResult(caseFile.evidenceGenerator(value).result);
  }

  function toggleBlock(id: string) {
    setVerdict(null);
    setSelectedBlocks((current) => current.includes(id) ? current.filter((blockId) => blockId !== id) : [...current, id]);
  }

  function requestHint() {
    const next = Math.min(hintIndex + 1, caseFile.hints.length - 1);
    setHintIndex(next);
    if (next !== hintIndex) {
      setProgress((current) => ({
        ...current,
        hintsByCase: { ...current.hintsByCase, [caseFile.id]: (current.hintsByCase[caseFile.id] ?? 0) + 1 },
      }));
    }
  }

  function submit() {
    const chosenStrategy = strategy || ((caseFile.strategyOptions?.length ?? 0) <= 1 ? caseFile.allowedStrategies[0] : '');
    const result = verifyStructuredProof(caseFile, {
      selectedBlocks,
      strategy: chosenStrategy,
      auditLine,
      objection,
      evidenceValue,
      claimAnswers,
      explanation,
    });
    setVerdict(result);
    setPhase(3);
    setProgress((current) => {
      const firstCompletion = result.accepted && !current.completed.includes(caseFile.id);
      return {
        ...current,
        attemptsByCase: { ...current.attemptsByCase, [caseFile.id]: (current.attemptsByCase[caseFile.id] ?? 0) + 1 },
        completed: firstCompletion ? [...current.completed, caseFile.id] : current.completed,
        stepsFiledByCase: firstCompletion ? { ...current.stepsFiledByCase, [caseFile.id]: selectedBlocks.length } : current.stepsFiledByCase,
        methodsChosen: result.accepted ? { ...current.methodsChosen, [caseFile.id]: chosenStrategy } : current.methodsChosen,
      };
    });
  }

  if (showIntro) {
    return (
      <IntroScreen
        onBegin={() => { openCase(0, true); setShowIntro(false); }}
        onSkip={() => { openCase(0, false); setShowIntro(false); }}
      />
    );
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="border-b border-white/10 bg-[#142e2b] text-[#fff9e9]">
        <div className="mx-auto flex min-h-16 max-w-5xl items-center justify-between gap-3 px-4 py-2 sm:px-6">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-full border border-[#d6b568]/45 bg-[#0e2421] text-[#e3c675]"><Scale className="size-5" /></span>
            <div><p className="font-heading text-lg font-semibold">Court of Proof</p><p className="hidden text-[10px] font-semibold uppercase tracking-[0.16em] text-[#dacb9d] sm:block">{caseFile.campaignStage}</p></div>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden rounded-full border border-[#d6b568]/35 bg-black/10 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#eadba8] md:inline">Structured judge · Lean not running</span>
            <Button variant="outline" onClick={() => setDocketOpen(true)} className="border-white/15 bg-white/5 text-white hover:bg-white/10 hover:text-white"><List /> Cases</Button>
            <button onClick={() => setDictionaryOpen(true)} className="grid size-9 place-items-center rounded-lg border border-white/15 bg-white/5 hover:bg-white/10" aria-label="Open vocabulary"><BookOpen className="size-4" /></button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-9">
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#8a6a2e]">Case {String(caseIndex + 1).padStart(3, '0')} · {caseFile.subtitle}</p>
            <h1 className="mt-1 font-heading text-2xl font-semibold sm:text-3xl">{caseFile.title}</h1>
          </div>
          <button onClick={() => openCase(caseIndex, tutorialActive)} className="flex items-center gap-1.5 text-xs font-semibold text-[#736a5a] hover:text-[#353129]"><RotateCcw className="size-3.5" /> Reset case</button>
        </div>

        <StepRail phase={phase} maxPhase={verdict ? 3 : phase} onSelect={setPhase} />

        {tutorialActive && phase < 3 && (
          <output className="tutorial-callout">
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-[#d8b85f] font-bold text-[#173b36]">{phase + 1}</span>
            <div><p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#d9c895]">Tutorial · focus here</p><p className="mt-0.5 text-sm text-[#fff9e9]">{phase === 0 ? 'First translate the claim: who is it about, and what does “every” require?' : phase === 1 ? 'Now investigate. Try 2—the smallest prime—and see whether it breaks the claim.' : 'File facts in any order that respects their logical dependencies.'}</p></div>
          </output>
        )}

        <div className={`mt-5 ${tutorialActive && phase < 3 ? 'tutorial-focus' : ''}`}>
          {phase === 0 && (
            <ClaimStep
              caseFile={caseFile}
              plainEnglish={plainEnglish}
              setPlainEnglish={setPlainEnglish}
              answers={claimAnswers}
              answerClaim={answerClaim}
              onContinue={() => setPhase(1)}
            />
          )}
          {phase === 1 && (
            <EvidenceStep
              caseFile={caseFile}
              evidenceInput={evidenceInput}
              setEvidenceInput={setEvidenceInput}
              evidenceValue={evidenceValue}
              evidenceResult={evidenceResult}
              testEvidence={testEvidence}
              onBack={() => setPhase(0)}
              onContinue={() => setPhase(2)}
            />
          )}
          {phase === 2 && (
            <ArgumentStep
              caseFile={caseFile}
              scaffoldLevel={scaffoldLevel}
              chosenBlocks={chosenBlocks}
              selectedBlocks={selectedBlocks}
              toggleBlock={toggleBlock}
              strategy={strategy}
              setStrategy={(value) => {
                setStrategy(value);
                setSelectedBlocks([]);
                setExplanation({});
                setVerdict(null);
              }}
              auditLine={auditLine}
              setAuditLine={setAuditLine}
              objection={objection}
              setObjection={setObjection}
              explanation={explanation}
              setExplanation={setExplanation}
              hintIndex={hintIndex}
              requestHint={requestHint}
              verdict={verdict}
              onBack={() => setPhase(1)}
              onSubmit={submit}
            />
          )}
          {phase === 3 && verdict && (
            <VerdictStep
              caseFile={caseFile}
              verdict={verdict}
              tutorialActive={tutorialActive}
              onRevise={() => setPhase(2)}
              onNext={() => openCase(Math.min(caseIndex + 1, cases.length - 1), false)}
              hasNext={caseIndex < cases.length - 1}
            />
          )}
        </div>
      </section>

      {docketOpen && <CaseDrawer caseIndex={caseIndex} progress={progress} independence={independence} previewMode={previewMode} isUnlocked={isUnlocked} onSelect={(index) => openCase(index, false)} onClose={() => setDocketOpen(false)} />}
      {dictionaryOpen && <Dictionary caseFile={caseFile} onClose={() => setDictionaryOpen(false)} />}
    </main>
  );
}

function IntroScreen({ onBegin, onSkip }: { onBegin: () => void; onSkip: () => void }) {
  const steps = [
    { number: '1', title: 'Read the claim', text: 'Identify the domain and what must be shown.' },
    { number: '2', title: 'Test evidence', text: 'Investigate—without mistaking examples for proof.' },
    { number: '3', title: 'Make your case', text: 'Connect supported facts to the verdict.' },
  ];
  return (
    <main className="grid min-h-screen place-items-center bg-[#142e2b] px-4 py-10 text-[#282820]">
      <section className="w-full max-w-3xl rounded-2xl border border-[#d7cdb8] bg-[#fffaf0] p-6 shadow-2xl sm:p-10">
        <div className="mx-auto max-w-xl text-center">
          <span className="mx-auto grid size-12 place-items-center rounded-full bg-[#173b36] text-[#e3c675]"><Scale className="size-6" /></span>
          <p className="mt-5 text-[11px] font-bold uppercase tracking-[0.18em] text-[#8a6a2e]">Welcome, Junior Associate</p>
          <h1 className="mt-2 font-heading text-3xl font-semibold sm:text-4xl">Your job is simple.</h1>
          <p className="mx-auto mt-3 max-w-md text-base leading-relaxed text-[#6b6559]">Decide whether a mathematical claim is true, then support your verdict.</p>
        </div>
        <div className="mt-8 grid gap-3 sm:grid-cols-3">
          {steps.map((step) => <article key={step.number} className="rounded-xl border border-[#ddd2bc] bg-white p-4"><span className="grid size-7 place-items-center rounded-full bg-[#e9dfc9] text-xs font-bold text-[#725b2e]">{step.number}</span><h2 className="mt-3 font-heading text-lg font-semibold">{step.title}</h2><p className="mt-1 text-sm leading-relaxed text-[#6b6559]">{step.text}</p></article>)}
        </div>
        <Button onClick={onBegin} className="mx-auto mt-8 flex h-11 bg-[#d8b85f] px-6 font-bold text-[#19312e] hover:bg-[#e4c975]">Start the 3-minute tutorial <ArrowRight /></Button>
        <button onClick={onSkip} className="mx-auto mt-4 block text-xs font-semibold text-[#746c5e] underline-offset-4 hover:underline">Start without tutorial guidance</button>
        <p className="mt-6 text-center text-[10px] font-semibold uppercase tracking-wide text-[#8a8172]">Verdicts use a structured checker · Lean 4 is prepared but not running</p>
      </section>
    </main>
  );
}

function StepRail({ phase, maxPhase, onSelect }: { phase: number; maxPhase: number; onSelect: (phase: number) => void }) {
  return (
    <nav aria-label="Case steps" className="grid grid-cols-4 overflow-hidden rounded-xl border border-[#d7cdb8] bg-[#eee7d8]">
      {phaseLabels.map((label, index) => (
        <button key={label} aria-label={`${index + 1}. ${label}`} disabled={index > maxPhase} onClick={() => onSelect(index)} className={`flex min-h-14 items-center justify-center gap-2 border-r border-[#d7cdb8] px-2 text-center last:border-r-0 ${index === phase ? 'bg-[#fffaf0] text-[#173b36] shadow-inner' : index < phase ? 'bg-[#e8f0e8] text-[#315f50]' : 'text-[#8d8576]'}`}>
          <span className={`grid size-6 shrink-0 place-items-center rounded-full text-xs font-bold ${index <= phase ? 'bg-[#315f50] text-white' : 'bg-[#d8cebc]'}`}>{index < phase ? <Check className="size-3.5" /> : index + 1}</span>
          <span className="sr-only sm:not-sr-only sm:text-xs sm:font-bold">{label}</span>
        </button>
      ))}
    </nav>
  );
}

function ClaimStep({ caseFile, plainEnglish, setPlainEnglish, answers, answerClaim, onContinue }: { caseFile: ProofCase; plainEnglish: boolean; setPlainEnglish: (value: boolean) => void; answers: Record<string, string>; answerClaim: (id: string, answer: string) => void; onContinue: () => void }) {
  const ready = (caseFile.claimQuestions ?? []).every((question) => answers[question.id] === question.answer);
  return (
    <section className="paper-card mx-auto max-w-3xl overflow-hidden">
      <div className="flex items-center justify-between border-b border-[#ded4bd] px-5 py-3">
        <p className="eyebrow">Claim before the court</p>
        <div className="flex rounded-lg border border-[#cbbd9c] bg-[#f6f0e3] p-0.5 text-[11px] font-semibold"><button aria-pressed={plainEnglish} onClick={() => setPlainEnglish(true)} className={`rounded-md px-2.5 py-1 ${plainEnglish ? 'bg-white shadow-sm' : ''}`}>Plain English</button><button aria-pressed={!plainEnglish} onClick={() => setPlainEnglish(false)} className={`rounded-md px-2.5 py-1 ${!plainEnglish ? 'bg-white shadow-sm' : ''}`}>Symbols</button></div>
      </div>
      <div className="px-6 py-8 text-center sm:px-10"><p className="math-display">{plainEnglish ? caseFile.plainEnglish : caseFile.claim}</p></div>
      <div className="border-y border-[#ded4bd] bg-[#f7f1e5] px-5 py-4"><p className="eyebrow">Domain · who this is about</p><p className="mt-1 text-sm font-semibold">{caseFile.domain}</p></div>
      {(caseFile.claimQuestions ?? []).length > 0 && <div className="space-y-5 p-5 sm:p-6">
        <p className="eyebrow">Check your reading</p>
        {caseFile.claimQuestions?.map((question) => {
          const chosen = answers[question.id];
          const correct = chosen === question.answer;
          return <fieldset key={question.id}><legend className="text-sm font-semibold">{question.prompt}</legend><div className="mt-2 grid gap-2 sm:grid-cols-3">{question.options.map((option) => <button type="button" key={option} onClick={() => answerClaim(question.id, option)} aria-pressed={chosen === option} className={`rounded-lg border p-3 text-left text-sm ${chosen === option ? correct ? 'border-[#64886d] bg-[#edf4ea]' : 'border-[#aa6755] bg-[#fff0e9]' : 'border-[#d3c6aa] bg-white hover:border-[#a98032]'}`}>{option}</button>)}</div>{chosen && <p className={`mt-2 text-xs leading-relaxed ${correct ? 'text-[#41664f]' : 'text-[#934b3c]'}`}>{correct ? question.explanation : 'Not quite. Compare the wording with the domain and quantifier, then try again.'}</p>}</fieldset>;
        })}
      </div>}
      <div className="flex items-center justify-end gap-3 p-5"><Button onClick={onContinue} disabled={!ready} className="h-10 bg-[#173b36] px-5 text-white">Continue to evidence <ArrowRight /></Button></div>
    </section>
  );
}

function EvidenceStep({ caseFile, evidenceInput, setEvidenceInput, evidenceValue, evidenceResult, testEvidence, onBack, onContinue }: { caseFile: ProofCase; evidenceInput: string; setEvidenceInput: (value: string) => void; evidenceValue: number | null; evidenceResult: string; testEvidence: () => void; onBack: () => void; onContinue: () => void }) {
  const decisiveReady = caseFile.requiredEvidence === undefined || evidenceValue === caseFile.requiredEvidence;
  const ready = evidenceValue !== null && decisiveReady;
  return (
    <section className="paper-card mx-auto max-w-3xl p-5 sm:p-7">
      <div className="mx-auto max-w-xl text-center"><span className="mx-auto grid size-10 place-items-center rounded-full bg-[#eaddbd] text-[#765719]"><FlaskConical className="size-5" /></span><p className="mt-4 eyebrow">Evidence lab</p><h2 className="mt-1 font-heading text-2xl font-semibold">Investigate one valid case</h2><p className="mt-2 text-sm leading-relaxed text-[#6c6559]">{caseFile.evidencePrompt ?? 'Try one value from the stated domain.'}</p></div>
      <div className="mx-auto mt-6 max-w-md">
        <div className="flex gap-2"><input value={evidenceInput} onChange={(event) => setEvidenceInput(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && testEvidence()} inputMode={caseFile.evidenceKind === 'real' ? 'decimal' : 'numeric'} aria-label="Number to test" placeholder="Enter one number…" className="h-11 min-w-0 flex-1 rounded-lg border border-[#cfc5b0] bg-white px-3 text-base outline-none focus:border-[#8a6a2e] focus:ring-2 focus:ring-[#d7b762]/20" /><Button onClick={testEvidence} className="h-11 bg-[#173b36] px-5 text-white">Test it</Button></div>
        {evidenceResult && <output className={`mt-4 block rounded-xl border p-4 text-sm leading-relaxed ${evidenceValue === null ? 'border-[#d5a08f] bg-[#fff0e9] text-[#794238]' : 'border-[#b8cdbb] bg-[#edf4ea] text-[#344b40]'}`}>{evidenceResult}</output>}
        <p className="mt-3 text-xs leading-relaxed text-[#776f61]"><strong>Evidence is not proof:</strong> examples help you investigate. One counterexample can defeat “every,” but supporting examples cannot establish “every.”</p>
      </div>
      <div className="mt-7 flex items-center justify-between gap-3 border-t border-[#e1d8c6] pt-5"><Button variant="ghost" onClick={onBack}><ArrowLeft /> Back</Button><div className="text-right"><Button onClick={onContinue} disabled={!ready} className="h-10 bg-[#173b36] px-5 text-white">Continue to argument <ArrowRight /></Button>{!ready && caseFile.requiredEvidence !== undefined && <p className="mt-1.5 text-[11px] text-[#8a6a2e]">Find the decisive counterexample first.</p>}</div></div>
    </section>
  );
}

function CaseBoard({ caseFile }: { caseFile: ProofCase }) {
  return <section aria-labelledby="case-board-title" className="mb-5 rounded-xl border border-[#d8cdb6] bg-[#f7f1e5] p-4"><div className="mb-3 flex items-center gap-2"><LinkIcon className="size-4 text-[#7b6129]" /><p id="case-board-title" className="eyebrow">Case board · dependency chain</p></div><div className="dependency-chain">{caseFile.facts.map((fact, index) => <div key={fact.label} className="contents"><article className={`fact-card ${fact.state === 'goal' ? 'pending' : 'established'}`}><span className="fact-kicker">{fact.label}</span><strong>{fact.value}</strong><small>{fact.detail}</small></article>{index < caseFile.facts.length - 1 && <ChevronRight aria-hidden="true" className="chain-arrow" />}</div>)}</div></section>;
}

type ArgumentProps = {
  caseFile: ProofCase;
  scaffoldLevel: 'guided' | 'supported' | 'independent';
  chosenBlocks: (ProofCase['proofTemplate']['blocks'][number] | undefined)[];
  selectedBlocks: string[];
  toggleBlock: (id: string) => void;
  strategy: string;
  setStrategy: (value: string) => void;
  auditLine: number | null;
  setAuditLine: (line: number) => void;
  objection: string;
  setObjection: (value: string) => void;
  explanation: Record<string, string>;
  setExplanation: (value: Record<string, string>) => void;
  hintIndex: number;
  requestHint: () => void;
  verdict: Verdict | null;
  onBack: () => void;
  onSubmit: () => void;
};

function ArgumentStep({ caseFile, scaffoldLevel, chosenBlocks, selectedBlocks, toggleBlock, strategy, setStrategy, auditLine, setAuditLine, objection, setObjection, explanation, setExplanation, hintIndex, requestHint, verdict, onBack, onSubmit }: ArgumentProps) {
  const methods = caseFile.strategyOptions ?? caseFile.allowedStrategies;
  const activeRoute = caseFile.proofTemplate.routes?.find((route) => route.strategy === strategy);
  const opening = activeRoute?.opening ?? caseFile.proofTemplate.opening;
  const routeBlocks = caseFile.proofTemplate.routes
    ? activeRoute
      ? caseFile.proofTemplate.blocks.filter((block) => activeRoute.solution.includes(block.id) || Boolean(block.objection))
      : []
    : caseFile.proofTemplate.blocks;
  return (
    <section className="paper-card mx-auto max-w-3xl p-5 sm:p-7">
      <div className="mb-5"><p className="eyebrow">Your argument · {scaffoldLevel} support</p><h2 className="mt-1 font-heading text-2xl font-semibold">{caseFile.proofTemplate.mode === 'audit' ? 'Object to opposing counsel' : 'Connect the facts to the verdict'}</h2><p className="mt-2 text-sm text-[#6c6559]">{caseFile.proofTemplate.instruction}</p></div>
      <CaseBoard caseFile={caseFile} />
      {methods.length > 1 && caseFile.proofTemplate.mode !== 'audit' && <fieldset className="mb-5 rounded-xl border border-[#d8cdb6] bg-[#f7f1e5] p-4"><legend className="eyebrow px-1">Choose the best method</legend><div className="mt-2 flex flex-wrap gap-2">{methods.map((method) => <button type="button" key={method} onClick={() => setStrategy(method)} aria-pressed={strategy === method} className={`rounded-lg border px-3 py-2 text-sm font-semibold ${strategy === method ? 'border-[#315f50] bg-[#e8f0e8] text-[#244b40]' : 'border-[#d5cab4] bg-white'}`}>{method}</button>)}</div></fieldset>}
      {caseFile.proofTemplate.mode === 'audit'
        ? <AuditWorkspace caseFile={caseFile} auditLine={auditLine} setAuditLine={setAuditLine} objection={objection} setObjection={setObjection} />
        : <>
          <div className="space-y-2">
            {opening.map((line, index) => <div key={line} className="proof-line established"><span>{index + 1}</span><p>{line}</p><span className="text-[9px] font-bold uppercase tracking-wide text-[#6f756b]">Given</span></div>)}
            {chosenBlocks.map((block, index) => {
              if (!block) return null;
              const needsSupport = verdict?.problemStepId === block.id;
              return <button key={block.id} onClick={() => toggleBlock(block.id)} className={`proof-line selected ${needsSupport ? 'needs-support' : ''}`}><span>{opening.length + index + 1}</span><p>{block.text}{scaffoldLevel !== 'independent' && <small className="mt-1 block text-[#746b5b]">Because: {block.support}</small>}</p><span className={`text-[9px] font-bold uppercase tracking-wide ${needsSupport ? 'text-[#9a3f30]' : 'text-[#8a6a2e]'}`}>{needsSupport ? 'Needs support' : 'Remove'}</span></button>;
            })}
          </div>
          <div className="mt-5"><p className="mb-2 eyebrow">Choose the next supported line</p>{caseFile.proofTemplate.routes && !activeRoute && <p className="rounded-lg border border-[#d7cdb8] bg-[#f7f1e5] p-3 text-sm text-[#6c6559]">Choose a proof method to open its matching argument route.</p>}<div className="grid gap-2 sm:grid-cols-2">{routeBlocks.filter((block) => !selectedBlocks.includes(block.id)).map((block) => {
            const unmet = (block.requires ?? []).filter((id) => !selectedBlocks.includes(id));
            const status = scaffoldLevel === 'guided'
              ? block.objection ? 'Test this line carefully' : unmet.length ? 'Needs an earlier fact' : 'Supported so far'
              : scaffoldLevel === 'supported' ? 'Proposed line' : '';
            return <button key={block.id} onClick={() => toggleBlock(block.id)} className="rounded-lg border border-[#d3c6aa] bg-white p-3 text-left text-sm leading-relaxed hover:border-[#a98032]">{status && <span className={`mb-1 block text-[9px] font-bold uppercase tracking-[0.12em] ${unmet.length && scaffoldLevel === 'guided' ? 'text-[#986247]' : 'text-[#527363]'}`}>{status}</span>}{block.text}{scaffoldLevel === 'guided' && <small className="mt-1.5 block text-[#817765]">Justification: {block.support}</small>}</button>;
          })}</div></div>
          {(caseFile.explanationFields ?? []).length > 0 && <fieldset className="mt-6 rounded-xl border border-[#cbbd9c] bg-[#fbf7ed] p-4"><legend className="px-2 font-heading text-lg font-semibold">Explain the argument in four parts</legend><p className="mb-4 text-xs leading-relaxed text-[#71695b]">The judge checks for the mathematical ideas named by each sentence frame. Complete sentences are required.</p><div className="grid gap-4 sm:grid-cols-2">{caseFile.explanationFields?.map((field) => <label key={field.id} className="block"><span className="eyebrow">{field.label}</span><span className="mt-1 block text-xs text-[#756d60]">{field.sentenceFrame}</span><textarea value={explanation[field.id] ?? ''} onChange={(event) => setExplanation({ ...explanation, [field.id]: event.target.value })} aria-invalid={verdict?.missingExplanationField === field.id} className={`mt-2 min-h-24 w-full rounded-lg border bg-white p-3 text-sm outline-none focus:border-[#8a6a2e] ${verdict?.missingExplanationField === field.id ? 'border-[#b85d4b]' : 'border-[#cfc5b0]'}`} /></label>)}</div></fieldset>}
        </>}
      <div className="mt-5 rounded-xl border border-[#dfd5c0] bg-[#f4efe3] p-4"><button onClick={requestHint} className="flex items-center gap-2 text-sm font-semibold text-[#6d5525]"><CircleHelp className="size-4" /> Need a chamber hint?</button>{hintIndex >= 0 && <p className="mt-2 text-sm leading-relaxed text-[#5e574b]">{caseFile.hints[hintIndex]}</p>}</div>
      <div className="mt-6 flex items-center justify-between border-t border-[#e1d8c6] pt-5"><Button variant="ghost" onClick={onBack}><ArrowLeft /> Back</Button><Button onClick={onSubmit} className="h-10 bg-[#d8b85f] px-5 font-bold text-[#19312e] hover:bg-[#e4c975]">Submit to judge <Gavel /></Button></div>
    </section>
  );
}

function VerdictStep({ caseFile, verdict, tutorialActive, onRevise, onNext, hasNext }: { caseFile: ProofCase; verdict: Verdict; tutorialActive: boolean; onRevise: () => void; onNext: () => void; hasNext: boolean }) {
  const missingSteps = (verdict.missingStepIds ?? []).map((id) => caseFile.proofTemplate.blocks.find((block) => block.id === id)).filter(Boolean);
  return (
    <section className={`mx-auto max-w-2xl overflow-hidden rounded-2xl border text-[#fff9e9] shadow-xl ${verdict.accepted ? 'border-[#709c78] bg-[#174638]' : 'border-[#995746] bg-[#4a2723]'}`}>
      <div className="px-6 py-8 text-center sm:px-10"><span className="mx-auto grid size-14 place-items-center rounded-full border border-white/15 bg-black/10 text-[#e0c16c]">{verdict.accepted ? <ShieldCheck className="size-7" /> : <Gavel className="size-7" />}</span>{tutorialActive && verdict.accepted && <p className="mt-5 text-[10px] font-bold uppercase tracking-[0.17em] text-[#d9c895]">Tutorial complete</p>}<p className="mt-5 text-[10px] font-bold uppercase tracking-[0.15em] text-[#d9c895]">Structured proof checker · Lean theorem prepared, not executed</p><h2 className="mt-3 font-heading text-2xl font-semibold sm:text-3xl">{verdict.heading}</h2><p className="mx-auto mt-3 max-w-lg text-sm leading-relaxed text-[#e6dfce]">{verdict.message}</p>{missingSteps.length > 0 && <div className="mx-auto mt-5 max-w-lg rounded-lg border border-white/10 bg-black/10 p-4 text-left"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#ffd0b8]">Still needed before the conclusion</p><ul className="mt-2 space-y-2 text-sm text-white">{missingSteps.map((step) => step && <li key={step.id} className="flex gap-2"><span>•</span><span>{step.text}<small className="mt-0.5 block text-[#d9c895]">Justification: {step.support}</small></span></li>)}</ul></div>}{verdict.objection && missingSteps.length === 0 && <div className="mx-auto mt-5 max-w-sm rounded-lg border border-white/10 bg-black/10 p-3"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#ffd0b8]">Objection category</p><p className="mt-1 font-semibold">{verdict.objection}</p></div>}</div>
      <div className="border-t border-white/10 bg-black/10 px-6 py-5"><p className="text-center text-xs text-[#d9c895]">{caseFile.lesson}</p><div className="mt-4 flex justify-center gap-3">{!verdict.accepted && <Button onClick={onRevise} className="h-10 bg-white/10 text-white hover:bg-white/15"><ArrowLeft /> Revise argument</Button>}{verdict.accepted && hasNext && <Button onClick={onNext} className="h-10 bg-[#d8b85f] px-5 font-bold text-[#19312e] hover:bg-[#e4c975]">Call next case <ArrowRight /></Button>}</div></div>
    </section>
  );
}

function AuditWorkspace({ caseFile, auditLine, setAuditLine, objection, setObjection }: { caseFile: ProofCase; auditLine: number | null; setAuditLine: (line: number) => void; objection: string; setObjection: (value: string) => void }) {
  return <div className="grid gap-5 md:grid-cols-[1.2fr_.8fr]"><div className="space-y-2">{caseFile.proofTemplate.opening.map((line, index) => <button key={line} onClick={() => setAuditLine(index + 1)} aria-pressed={auditLine === index + 1} className={`proof-line choice ${auditLine === index + 1 ? 'border-[#a5573f] bg-[#fff0e9]' : ''}`}><span>{index + 1}</span><p>{line.replace(/^Line \d+\.\s*/, '')}</p>{auditLine === index + 1 ? <FileSearch className="size-4 text-[#a5573f]" /> : <span>?</span>}</button>)}</div><div><label htmlFor="objection" className="eyebrow">Name the objection</label><select id="objection" value={objection} onChange={(event) => setObjection(event.target.value)} className="mt-2 h-10 w-full rounded-lg border border-[#cfc5b0] bg-white px-3 text-sm"><option value="">Choose a category…</option>{objectionCategories.map((category) => <option key={category} value={category}>{category}</option>)}</select><div className="mt-3 space-y-2 text-xs leading-relaxed text-[#72695b]"><p><strong>First locate:</strong> where does support first break?</p><p><strong>Then classify:</strong> what exact rule was violated?</p></div></div></div>;
}

function CaseDrawer({ caseIndex, progress, independence, previewMode, isUnlocked, onSelect, onClose }: { caseIndex: number; progress: ProgressState; independence: number; previewMode: boolean; isUnlocked: (index: number) => boolean; onSelect: (index: number) => void; onClose: () => void }) {
  const attempts = Object.values(progress.attemptsByCase).reduce((total, count) => total + count, 0);
  return <div className="fixed inset-0 z-50"><button aria-label="Close cases" onClick={onClose} className="absolute inset-0 bg-black/45" /><dialog open aria-labelledby="campaign-title" className="absolute right-0 top-0 m-0 ml-auto h-full w-[min(90vw,410px)] overflow-auto border-0 bg-[#f0eadb] p-0 text-inherit shadow-2xl"><div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#d1c6b0] bg-[#f0eadb]/95 px-5 py-4 backdrop-blur"><div><p className="eyebrow">Campaign</p><h2 id="campaign-title" className="font-heading text-xl font-semibold">Choose a case</h2></div><button onClick={onClose} aria-label="Close cases"><X className="size-5" /></button></div><div className="p-4"><div className="mb-5 rounded-xl border border-[#cfc4aa] bg-[#e8dfcc] p-4"><div className="flex items-center justify-between"><span className="text-sm font-semibold">Mathematical independence</span><strong>{independence}%</strong></div><Progress value={independence} className="mt-2 [&_[data-slot=progress-indicator]]:bg-[#315f50] [&_[data-slot=progress-track]]:bg-[#cdc1aa]" /><p className="mt-2 text-xs text-[#70685a]">{progress.completed.length} of {cases.length} cases complete · {attempts} arguments filed</p><p className="mt-1 text-[11px] leading-relaxed text-[#7c715f]">Independent means accepted on the first filing, with no claim error or structural hint.</p>{previewMode && <p className="mt-2 rounded-md bg-[#fff7df] p-2 text-[11px] font-semibold text-[#76591e]">Teacher preview is on: every case is unlocked.</p>}</div><nav aria-label="Campaign cases" className="space-y-2">{cases.map((item, index) => { const done = progress.completed.includes(item.id); const unlocked = isUnlocked(index); return <button key={item.id} disabled={!unlocked} onClick={() => onSelect(index)} className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left ${index === caseIndex ? 'border-[#b9933f] bg-[#fffaf0]' : unlocked ? 'border-transparent hover:bg-white/50' : 'cursor-not-allowed border-transparent opacity-55'}`}><span className={`grid size-8 shrink-0 place-items-center rounded-full text-xs font-bold ${done ? 'bg-[#dbe9d9] text-[#315f50]' : 'bg-[#e1d8c5]'}`}>{done ? <Check className="size-4" /> : unlocked ? index + 1 : <Lock className="size-3.5" />}</span><span><span className="block text-[9px] font-bold uppercase tracking-[0.13em] text-[#817664]">{item.campaignStage} · {item.scaffoldLevel ?? 'supported'}</span><strong className="text-sm">{item.title}</strong></span>{unlocked && <ChevronRight className="ml-auto size-4 text-[#968b77]" />}</button>; })}</nav></div></dialog></div>;
}

const courtroomWords = [
  { term: 'Claim', meaning: 'The mathematical statement under review.' },
  { term: 'Evidence', meaning: 'Examples used to investigate. Supporting examples are not a general proof.' },
  { term: 'Proof', meaning: 'A complete chain of justified statements.' },
  { term: 'Objection', meaning: 'The exact reason a proof line is invalid or unsupported.' },
  { term: 'Q.E.D.', meaning: 'The argument is complete: the verdict sought has been established.' },
];

function Dictionary({ caseFile, onClose }: { caseFile: ProofCase; onClose: () => void }) {
  return <div className="fixed inset-0 z-[60]"><button aria-label="Close vocabulary" onClick={onClose} className="absolute inset-0 bg-[#102623]/65 backdrop-blur-sm" /><dialog open aria-labelledby="dictionary-title" className="absolute left-1/2 top-1/2 m-0 max-h-[80vh] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-2xl border border-[#d7cdb8] bg-[#fffaf0] p-0 text-inherit shadow-2xl"><div className="sticky top-0 flex items-center justify-between border-b border-[#ddd2bc] bg-[#fffaf0]/95 px-5 py-4 backdrop-blur"><div><p className="eyebrow">Vocabulary</p><h2 id="dictionary-title" className="font-heading text-xl font-semibold">Words for this case</h2></div><button onClick={onClose} aria-label="Close vocabulary"><X className="size-5" /></button></div><div className="space-y-3 p-5">{[...caseFile.definitions, ...courtroomWords].map((definition) => <article key={definition.term} className="rounded-xl border border-[#ddd2bc] bg-white p-4"><p className="font-heading font-semibold text-[#315f50]">{definition.term}</p><p className="mt-1 text-sm leading-relaxed text-[#655e52]">{definition.meaning}</p></article>)}</div></dialog></div>;
}
