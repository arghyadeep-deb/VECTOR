/**
 * VectorHUD.tsx
 * V.E.C.T.O.R. — JARVIS-style circular HUD splash screen
 *
 * Animated blueprint reactor with sweeping arc, tick marks, scanning dot,
 * and live status bar. Press q or Esc to dismiss.
 */
import React from 'react';
interface VectorHUDProps {
    model?: string;
    modelsOnline?: number;
    hasVectorMd?: boolean;
    /** Called on q / Esc — defaults to exit. Use to dismiss the splash. */
    onDismiss?: () => void;
    /** Disable animation (for static rendering, e.g. CI/testing) */
    static?: boolean;
}
declare const VectorHUD: React.FC<VectorHUDProps>;
export default VectorHUD;
