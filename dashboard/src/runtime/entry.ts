import { initSandboxRuntimeModular } from "./init";
import { fitTextFontSize } from "../text/fitTextFontSize";
import { getVariables } from "./getVariables";

type VectorWindow = Window & {
  __vectorRuntimeBootstrapped?: boolean;
  __vector?: {
    fitTextFontSize: typeof fitTextFontSize;
    getVariables: typeof getVariables;
  };
};

// Inline composition scripts can run before DOMContentLoaded.
// Ensure timeline registry exists at script evaluation time.
(window as VectorWindow).__timelines = (window as VectorWindow).__timelines || {};

// Expose runtime helpers immediately so composition scripts can use them
// before DOMContentLoaded (font sizing runs during script evaluation, and
// getVariables is read by composition setup before the timeline is built).
(window as VectorWindow).__vector = {
  fitTextFontSize,
  getVariables,
};

function bootstrapVectorRuntime(): void {
  const win = window as VectorWindow;
  if (win.__vectorRuntimeBootstrapped) {
    return;
  }
  win.__vectorRuntimeBootstrapped = true;
  initSandboxRuntimeModular();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootstrapVectorRuntime, { once: true });
} else {
  bootstrapVectorRuntime();
}
