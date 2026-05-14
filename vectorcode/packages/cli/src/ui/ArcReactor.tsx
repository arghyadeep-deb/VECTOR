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

type Size = 'small' | 'medium' | 'large';

interface ArcReactorProps {
  size?: Size;
  /** Whether to pulse the core (animated) — disabled by default */
  pulse?: boolean;
  /** Whether to show the "VECTOR" letters inside */
  showText?: boolean;
}

// Color layers (outer → core)
const LAYERS = {
  ringDim:    'gray',
  ringMid:    'cyan',
  ringBright: 'cyanBright',
  core:       'whiteBright',
} as const;

export const ArcReactor: React.FC<ArcReactorProps> = ({
  size = 'medium',
  pulse = false,
  showText = true,
}) => {
  if (size === 'small') return <ArcSmall />;
  if (size === 'large') return <ArcLarge showText={showText} />;
  return <ArcMedium showText={showText} />;
};

// ── Small: inline glyph (4 chars) ─────────────────────────────────────────────

const ArcSmall: React.FC = () => (
  <Text>
    <Text color={LAYERS.ringMid}>⟨</Text>
    <Text color={LAYERS.core} bold>◉</Text>
    <Text color={LAYERS.ringMid}>⟩</Text>
  </Text>
);

// ── Medium: banner reactor (~22w × 9h) ───────────────────────────────────────

const ArcMedium: React.FC<{ showText: boolean }> = ({ showText }) => {
  // 9-row design with concentric rings + V·E·C·T·O·R in core
  return (
    <Box flexDirection="column">
      {/* Row 1: outer top arc */}
      <Box>
        <Text color={LAYERS.ringDim}>      ╱─────────────╲      </Text>
      </Box>
      {/* Row 2: outer top */}
      <Box>
        <Text color={LAYERS.ringDim}>    ╱</Text>
        <Text color={LAYERS.ringMid}>  ╱─────────╲  </Text>
        <Text color={LAYERS.ringDim}>╲    </Text>
      </Box>
      {/* Row 3: middle layer top */}
      <Box>
        <Text color={LAYERS.ringDim}>   │</Text>
        <Text color={LAYERS.ringMid}>  │</Text>
        <Text color={LAYERS.ringBright}> ╭─────╮ </Text>
        <Text color={LAYERS.ringMid}>│  </Text>
        <Text color={LAYERS.ringDim}>│   </Text>
      </Box>
      {/* Row 4: VECTOR letters top half */}
      <Box>
        <Text color={LAYERS.ringDim}>   │</Text>
        <Text color={LAYERS.ringMid}>  │</Text>
        <Text color={LAYERS.ringBright}> │ </Text>
        <Text color={LAYERS.core} bold>
          {showText ? 'V·E·C' : '   '}
        </Text>
        <Text color={LAYERS.ringBright}> │ </Text>
        <Text color={LAYERS.ringMid}>│  </Text>
        <Text color={LAYERS.ringDim}>│   </Text>
      </Box>
      {/* Row 5: core middle */}
      <Box>
        <Text color={LAYERS.ringDim}>   │</Text>
        <Text color={LAYERS.ringMid}>  │</Text>
        <Text color={LAYERS.ringBright}> │ </Text>
        <Text color={LAYERS.core} bold>
          {showText ? 'T·O·R' : '   '}
        </Text>
        <Text color={LAYERS.ringBright}> │ </Text>
        <Text color={LAYERS.ringMid}>│  </Text>
        <Text color={LAYERS.ringDim}>│   </Text>
      </Box>
      {/* Row 6: middle layer bottom */}
      <Box>
        <Text color={LAYERS.ringDim}>   │</Text>
        <Text color={LAYERS.ringMid}>  │</Text>
        <Text color={LAYERS.ringBright}> ╰─────╯ </Text>
        <Text color={LAYERS.ringMid}>│  </Text>
        <Text color={LAYERS.ringDim}>│   </Text>
      </Box>
      {/* Row 7: outer bottom */}
      <Box>
        <Text color={LAYERS.ringDim}>    ╲</Text>
        <Text color={LAYERS.ringMid}>  ╲─────────╱  </Text>
        <Text color={LAYERS.ringDim}>╱    </Text>
      </Box>
      {/* Row 8: outer bottom arc */}
      <Box>
        <Text color={LAYERS.ringDim}>      ╲─────────────╱      </Text>
      </Box>
    </Box>
  );
};

// ── Large: splash screen (~36w × 13h) ────────────────────────────────────────

const ArcLarge: React.FC<{ showText: boolean }> = ({ showText }) => {
  return (
    <Box flexDirection="column">
      {/* Row 1: outer corona */}
      <Box>
        <Text color={LAYERS.ringDim}>          ▄▄▄▄▄▄▄▄▄▄▄▄▄          </Text>
      </Box>
      {/* Row 2 */}
      <Box>
        <Text color={LAYERS.ringDim}>       ▄</Text>
        <Text color={LAYERS.ringMid}>██████▀▀▀▀▀▀▀██████</Text>
        <Text color={LAYERS.ringDim}>▄       </Text>
      </Box>
      {/* Row 3 */}
      <Box>
        <Text color={LAYERS.ringDim}>     ▄</Text>
        <Text color={LAYERS.ringMid}>███▀</Text>
        <Text color={LAYERS.ringBright}>  ╭─────────╮  </Text>
        <Text color={LAYERS.ringMid}>▀███</Text>
        <Text color={LAYERS.ringDim}>▄     </Text>
      </Box>
      {/* Row 4 */}
      <Box>
        <Text color={LAYERS.ringMid}>    ██▀</Text>
        <Text color={LAYERS.ringBright}>   ╭─────────╮   </Text>
        <Text color={LAYERS.ringMid}>▀██    </Text>
      </Box>
      {/* Row 5 */}
      <Box>
        <Text color={LAYERS.ringMid}>   ██</Text>
        <Text color={LAYERS.ringBright}>    │ </Text>
        <Text color={LAYERS.core} bold>
          {showText ? 'V · E · C' : '         '}
        </Text>
        <Text color={LAYERS.ringBright}> │    </Text>
        <Text color={LAYERS.ringMid}>██   </Text>
      </Box>
      {/* Row 6 — equator */}
      <Box>
        <Text color={LAYERS.ringMid}>  ██</Text>
        <Text color={LAYERS.ringBright}>     │ </Text>
        <Text color={LAYERS.core} bold>
          {showText ? '⟨▶⟩  CORE' : '         '}
        </Text>
        <Text color={LAYERS.ringBright}> │     </Text>
        <Text color={LAYERS.ringMid}>██  </Text>
      </Box>
      {/* Row 7 */}
      <Box>
        <Text color={LAYERS.ringMid}>   ██</Text>
        <Text color={LAYERS.ringBright}>    │ </Text>
        <Text color={LAYERS.core} bold>
          {showText ? 'T · O · R' : '         '}
        </Text>
        <Text color={LAYERS.ringBright}> │    </Text>
        <Text color={LAYERS.ringMid}>██   </Text>
      </Box>
      {/* Row 8 */}
      <Box>
        <Text color={LAYERS.ringMid}>    ██▄</Text>
        <Text color={LAYERS.ringBright}>   ╰─────────╯   </Text>
        <Text color={LAYERS.ringMid}>▄██    </Text>
      </Box>
      {/* Row 9 */}
      <Box>
        <Text color={LAYERS.ringDim}>     ▀</Text>
        <Text color={LAYERS.ringMid}>███▄</Text>
        <Text color={LAYERS.ringBright}>  ╰─────────╯  </Text>
        <Text color={LAYERS.ringMid}>▄███</Text>
        <Text color={LAYERS.ringDim}>▀     </Text>
      </Box>
      {/* Row 10 */}
      <Box>
        <Text color={LAYERS.ringDim}>       ▀</Text>
        <Text color={LAYERS.ringMid}>██████▄▄▄▄▄▄▄██████</Text>
        <Text color={LAYERS.ringDim}>▀       </Text>
      </Box>
      {/* Row 11: outer corona */}
      <Box>
        <Text color={LAYERS.ringDim}>          ▀▀▀▀▀▀▀▀▀▀▀▀▀          </Text>
      </Box>
    </Box>
  );
};
