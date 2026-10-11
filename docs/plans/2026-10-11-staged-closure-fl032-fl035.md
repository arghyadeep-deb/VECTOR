# FL-032 / FL-035 Staged Closure Plan

1. Add focused regressions for the API-only generic capability grant, media-root
   confinement (including sibling-prefix bypasses), and disabled paid providers.
2. Run those regressions against the current code and preserve the failing output.
3. Implement only the owner-decided gateway grant, shared media config root,
   per-tool confinement, and paid-provider disablement.
4. Update the one camera expectation and any directly conflicting legacy tool
   tests, then run focused and existing suites plus `py_compile` for every
   touched Python file.

