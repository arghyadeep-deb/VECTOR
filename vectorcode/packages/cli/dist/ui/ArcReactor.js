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
import { Box, Text } from 'ink';
// Color layers (outer → core)
const LAYERS = {
    ringDim: 'gray',
    ringMid: 'cyan',
    ringBright: 'cyanBright',
    core: 'whiteBright',
};
export const ArcReactor = ({ size = 'medium', pulse = false, showText = true, }) => {
    if (size === 'small')
        return React.createElement(ArcSmall, null);
    if (size === 'large')
        return React.createElement(ArcLarge, { showText: showText });
    return React.createElement(ArcMedium, { showText: showText });
};
// ── Small: inline glyph (4 chars) ─────────────────────────────────────────────
const ArcSmall = () => (React.createElement(Text, null,
    React.createElement(Text, { color: LAYERS.ringMid }, "\u27E8"),
    React.createElement(Text, { color: LAYERS.core, bold: true }, "\u25C9"),
    React.createElement(Text, { color: LAYERS.ringMid }, "\u27E9")));
// ── Medium: banner reactor (~22w × 9h) ───────────────────────────────────────
const ArcMedium = ({ showText }) => {
    // 9-row design with concentric rings + V·E·C·T·O·R in core
    return (React.createElement(Box, { flexDirection: "column" },
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringDim }, "      \u2571\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2572      ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringDim }, "    \u2571"),
            React.createElement(Text, { color: LAYERS.ringMid }, "  \u2571\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2572  "),
            React.createElement(Text, { color: LAYERS.ringDim }, "\u2572    ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringDim }, "   \u2502"),
            React.createElement(Text, { color: LAYERS.ringMid }, "  \u2502"),
            React.createElement(Text, { color: LAYERS.ringBright }, " \u256D\u2500\u2500\u2500\u2500\u2500\u256E "),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2502  "),
            React.createElement(Text, { color: LAYERS.ringDim }, "\u2502   ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringDim }, "   \u2502"),
            React.createElement(Text, { color: LAYERS.ringMid }, "  \u2502"),
            React.createElement(Text, { color: LAYERS.ringBright }, " \u2502 "),
            React.createElement(Text, { color: LAYERS.core, bold: true }, showText ? 'V·E·C' : '   '),
            React.createElement(Text, { color: LAYERS.ringBright }, " \u2502 "),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2502  "),
            React.createElement(Text, { color: LAYERS.ringDim }, "\u2502   ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringDim }, "   \u2502"),
            React.createElement(Text, { color: LAYERS.ringMid }, "  \u2502"),
            React.createElement(Text, { color: LAYERS.ringBright }, " \u2502 "),
            React.createElement(Text, { color: LAYERS.core, bold: true }, showText ? 'T·O·R' : '   '),
            React.createElement(Text, { color: LAYERS.ringBright }, " \u2502 "),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2502  "),
            React.createElement(Text, { color: LAYERS.ringDim }, "\u2502   ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringDim }, "   \u2502"),
            React.createElement(Text, { color: LAYERS.ringMid }, "  \u2502"),
            React.createElement(Text, { color: LAYERS.ringBright }, " \u2570\u2500\u2500\u2500\u2500\u2500\u256F "),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2502  "),
            React.createElement(Text, { color: LAYERS.ringDim }, "\u2502   ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringDim }, "    \u2572"),
            React.createElement(Text, { color: LAYERS.ringMid }, "  \u2572\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2571  "),
            React.createElement(Text, { color: LAYERS.ringDim }, "\u2571    ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringDim }, "      \u2572\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2571      "))));
};
// ── Large: splash screen (~36w × 13h) ────────────────────────────────────────
const ArcLarge = ({ showText }) => {
    return (React.createElement(Box, { flexDirection: "column" },
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringDim }, "          \u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2584          ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringDim }, "       \u2584"),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2588\u2588\u2588\u2588\u2588\u2588\u2580\u2580\u2580\u2580\u2580\u2580\u2580\u2588\u2588\u2588\u2588\u2588\u2588"),
            React.createElement(Text, { color: LAYERS.ringDim }, "\u2584       ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringDim }, "     \u2584"),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2588\u2588\u2588\u2580"),
            React.createElement(Text, { color: LAYERS.ringBright }, "  \u256D\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u256E  "),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2580\u2588\u2588\u2588"),
            React.createElement(Text, { color: LAYERS.ringDim }, "\u2584     ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringMid }, "    \u2588\u2588\u2580"),
            React.createElement(Text, { color: LAYERS.ringBright }, "   \u256D\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u256E   "),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2580\u2588\u2588    ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringMid }, "   \u2588\u2588"),
            React.createElement(Text, { color: LAYERS.ringBright }, "    \u2502 "),
            React.createElement(Text, { color: LAYERS.core, bold: true }, showText ? 'V · E · C' : '         '),
            React.createElement(Text, { color: LAYERS.ringBright }, " \u2502    "),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2588\u2588   ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringMid }, "  \u2588\u2588"),
            React.createElement(Text, { color: LAYERS.ringBright }, "     \u2502 "),
            React.createElement(Text, { color: LAYERS.core, bold: true }, showText ? '⟨▶⟩  CORE' : '         '),
            React.createElement(Text, { color: LAYERS.ringBright }, " \u2502     "),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2588\u2588  ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringMid }, "   \u2588\u2588"),
            React.createElement(Text, { color: LAYERS.ringBright }, "    \u2502 "),
            React.createElement(Text, { color: LAYERS.core, bold: true }, showText ? 'T · O · R' : '         '),
            React.createElement(Text, { color: LAYERS.ringBright }, " \u2502    "),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2588\u2588   ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringMid }, "    \u2588\u2588\u2584"),
            React.createElement(Text, { color: LAYERS.ringBright }, "   \u2570\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u256F   "),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2584\u2588\u2588    ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringDim }, "     \u2580"),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2588\u2588\u2588\u2584"),
            React.createElement(Text, { color: LAYERS.ringBright }, "  \u2570\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u256F  "),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2584\u2588\u2588\u2588"),
            React.createElement(Text, { color: LAYERS.ringDim }, "\u2580     ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringDim }, "       \u2580"),
            React.createElement(Text, { color: LAYERS.ringMid }, "\u2588\u2588\u2588\u2588\u2588\u2588\u2584\u2584\u2584\u2584\u2584\u2584\u2584\u2588\u2588\u2588\u2588\u2588\u2588"),
            React.createElement(Text, { color: LAYERS.ringDim }, "\u2580       ")),
        React.createElement(Box, null,
            React.createElement(Text, { color: LAYERS.ringDim }, "          \u2580\u2580\u2580\u2580\u2580\u2580\u2580\u2580\u2580\u2580\u2580\u2580\u2580          "))));
};
//# sourceMappingURL=ArcReactor.js.map