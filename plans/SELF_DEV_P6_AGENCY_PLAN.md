# SELF-DEV P6: Agency dispatch repair plan

## Scope

Repair the agency district's production free-text dispatch shape without
creating duplicate persona agents or changing permission tiers. The repair
must only answer unambiguous read questions: mutation-like or vague chat text
must retain the existing explicit unhandled-type error. It also closes the
Rule 1 hydration omissions in the agency's existing LLM call sites.

## Evidence

- `tests/test_agency_run_wiring.py` reproduces real governor-shaped tasks whose
  `type` is unmatched while `params.query` contains a question that existing
  methods can answer.
- `ClientManager.run()` and `PerformanceTracker.run()` currently return their
  generic unhandled-type error before consulting that query.

## Steps

1. Add deterministic, read-only query resolution that requires a question
   shape, a supported read intent, and relevant nouns; reject mutation verbs.
   Resolve multiple matching metric names as an explicit ambiguity, never by
   dict insertion order.
2. Change the regression assertions to prove returned values come from
   isolated client/metric records; cover vague, substring, and mutation-like
   queries plus ambiguity. Cleanup runs in `finally` blocks.
3. Prepend a real `ContextEngine.session_hydration_prompt()` system message to
   every agency LLM call and test the emitted message without mocking hydration.
4. Run the required test target and record only evidence-backed persona
   coverage and configuration claims in `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P6_AGENCY.md`.

## Guardrails

- No external action, permission-tier, manifest, or configuration change is
  part of this repair. The LLM changes only add required session hydration;
  they do not change provider routing or model selection.
- Do not claim a selected persona is real where no existing verifiable
  capability covers it; report the gap instead.
