# Dormant Feature Pile Audit Plan

1. Re-read each named implementation and identify its public entry points, registrations, side effects, and documented intent.
2. Search the entire repository, including tests and scripts, for imports, symbol references, dynamic registrations, command dispatch, and compatibility re-exports; distinguish meaningful execution from package-local references and documentation.
3. Inspect relevant git history for prior callers, compatibility intent, and recent changes that could make the backlog claim stale.
4. Classify each item as dead, owner decision, safety-sensitive, or actually live. Default ambiguous feature-shaped code to owner decision.
5. Immediately re-check references before deleting any dead item, remove only confirmed-dead files and orphaned imports, and leave all other code untouched.
6. Document every retained item with evidence and an actionable recommendation where required.
7. Compile every touched Python file, smoke-import affected packages, and run focused tests for deleted areas without collecting the full repository suite.

