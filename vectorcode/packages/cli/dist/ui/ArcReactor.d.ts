/**
 * ArcReactor — JARVIS-style chest reactor symbol with VECTOR text in the core.
 *
 * Renders a multi-layered concentric ring design with a glowing gradient
 * (dim cyan outer → cyan → bright cyan → white-bold core). Sized variants:
 *   - small:  inline header glyph (~4 cols)
 *   - medium: banner reactor (~22 cols × 9 rows)
 *   - large:  splash screen reactor (~36 cols × 13 rows)
 */
import React from 'react';
type Size = 'small' | 'medium' | 'large';
interface ArcReactorProps {
    size?: Size;
    /** Whether to pulse the core (animated) — disabled by default */
    pulse?: boolean;
    /** Whether to show the "VECTOR" letters inside */
    showText?: boolean;
}
export declare const ArcReactor: React.FC<ArcReactorProps>;
export {};
