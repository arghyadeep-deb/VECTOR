export interface PreviewZoomState {
  zoomPercent: number;
  panX: number;
  panY: number;
}

export const MIN_PREVIEW_ZOOM_PERCENT = 25;
export const MAX_PREVIEW_ZOOM_PERCENT = 400;
export const DEFAULT_PREVIEW_ZOOM: PreviewZoomState = {
  zoomPercent: 100,
  panX: 0,
  panY: 0,
};

const ZOOM_SENSITIVITY = 0.007;
const MAX_DELTA = 10;

export function toDomPrecision(value: number): number {
  return Math.round(value * 10000) / 10000;
}

export function clampPreviewZoomPercent(percent: number): number {
  if (!Number.isFinite(percent)) return 100;
  return Math.min(MAX_PREVIEW_ZOOM_PERCENT, Math.max(MIN_PREVIEW_ZOOM_PERCENT, percent));
}

export function getPreviewWheelZoomPercent(deltaY: number, currentZoomPercent: number): number {
  if (!Number.isFinite(deltaY)) return clampPreviewZoomPercent(currentZoomPercent);
  const clamped = Math.abs(deltaY) > MAX_DELTA ? MAX_DELTA * Math.sign(deltaY) : deltaY;
  const step = -clamped * ZOOM_SENSITIVITY;
  const current = clampPreviewZoomPercent(currentZoomPercent);
  return clampPreviewZoomPercent(current * Math.exp(step));
}

export function getNextPreviewZoomPercent(
  direction: "in" | "out",
  currentZoomPercent: number,
): number {
  const current = clampPreviewZoomPercent(currentZoomPercent);
  const multiplier = direction === "in" ? 1.25 : 0.8;
  return clampPreviewZoomPercent(current * multiplier);
}

export function clampPreviewPan(input: {
  panX: number;
  panY: number;
  zoomPercent: number;
  viewportWidth: number;
  viewportHeight: number;
}): Pick<PreviewZoomState, "panX" | "panY"> {
  const scale = clampPreviewZoomPercent(input.zoomPercent) / 100;
  if (scale <= 1) return { panX: 0, panY: 0 };

  const maxPanX = ((scale - 1) * input.viewportWidth) / 2;
  const maxPanY = ((scale - 1) * input.viewportHeight) / 2;
  return {
    panX: Math.min(maxPanX, Math.max(-maxPanX, input.panX)),
    panY: Math.min(maxPanY, Math.max(-maxPanY, input.panY)),
  };
}

export function resolvePreviewWheelZoom(input: {
  state: PreviewZoomState;
  deltaY: number;
  viewportWidth: number;
  viewportHeight: number;
}): PreviewZoomState {
  const nextZoomPercent = getPreviewWheelZoomPercent(
    input.deltaY,
    clampPreviewZoomPercent(input.state.zoomPercent),
  );
  const pan = clampPreviewPan({
    panX: input.state.panX,
    panY: input.state.panY,
    zoomPercent: nextZoomPercent,
    viewportWidth: input.viewportWidth,
    viewportHeight: input.viewportHeight,
  });

  return {
    zoomPercent: nextZoomPercent,
    ...pan,
  };
}
