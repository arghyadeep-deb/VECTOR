/**
 * VectorHUD.tsx
 * V.E.C.T.O.R. — JARVIS-style circular HUD splash screen
 *
 * Animated blueprint reactor with sweeping arc, tick marks, scanning dot,
 * and live status bar. Press q or Esc to dismiss.
 */

import React, { useState, useEffect } from 'react';
import { Box, Text, useApp, useInput } from 'ink';
import chalk from 'chalk';

// ─── Grid Constants ───────────────────────────────────────────────────────────
const COLS = 74;
const GRID_ROWS = 26;
const CX = 37;
const CY = 13;
const ASPECT = 0.48;
const OUTER_R = 11.5;
const TICK_R = 10.5;
const MID_R = 8.8;
const INNER_R = 6.5;

// ─── Color Palette ────────────────────────────────────────────────────────────
const C = {
  yellow: '#ffd700',
  cyan: '#00e5ff',
  cyanBright: '#40ffff',
  cyanMid: '#00aacc',
  cyanDim: '#006688',
  cyanDark: '#003344',
  bgDot: '#0d2233',
  white: '#e8f8ff',
  dimWhite: '#7aabb8',
  green: '#00ff88',
  orange: '#ff8800',
  gray: '#445566',
} as const;

interface Cell {
  char: string;
  color: string;
  bold: boolean;
}

// ─── Blueprint background pattern ─────────────────────────────────────────────
function isBlueprintDot(r: number, c: number, cx: number, cy: number, outerR: number): boolean {
  const dx = (c - cx) * ASPECT;
  const dy = r - cy;
  const dist = Math.sqrt(dx * dx + dy * dy);
  if (dist >= outerR - 2) return false;
  return c % 4 === 1 && r % 2 === 0;
}

// ─── Core frame builder ───────────────────────────────────────────────────────
function buildFrame(tick: number): Cell[][] {
  const grid: Cell[][] = Array.from({ length: GRID_ROWS }, () =>
    Array.from({ length: COLS }, () => ({ char: ' ', color: C.bgDot, bold: false })),
  );

  const set = (r: number, c: number, char: string, color: string, bold = false) => {
    if (r >= 0 && r < GRID_ROWS && c >= 0 && c < COLS) {
      grid[r][c] = { char, color, bold };
    }
  };

  // Blueprint background dots
  for (let r = 0; r < GRID_ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      if (isBlueprintDot(r, c, CX, CY, OUTER_R)) {
        set(r, c, '·', C.bgDot);
      }
    }
  }

  // Rings pass
  for (let r = 0; r < GRID_ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const dx = (c - CX) * ASPECT;
      const dy = r - CY;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const angle = ((Math.atan2(dy, dx) * 180) / Math.PI + 360) % 360;

      // OUTER RING — yellow arc + tick marks + dots
      if (Math.abs(dist - OUTER_R) < 0.82) {
        const arcStart = (tick * 2.5) % 360;
        const arcLen = 85;
        const arcEnd = (arcStart + arcLen) % 360;
        const inArc =
          arcStart <= arcEnd
            ? angle >= arcStart && angle <= arcEnd
            : angle >= arcStart || angle <= arcEnd;

        if (inArc) {
          set(r, c, '●', C.yellow);
        } else {
          set(r, c, '·', C.cyanDim);
        }
      }
      // TICK MARKS RING
      else if (Math.abs(dist - TICK_R) < 0.55) {
        const majorTick = angle % 45 < 6;
        const minorTick = angle % 15 < 4;
        if (majorTick) {
          set(r, c, '◆', C.cyan, true);
        } else if (minorTick) {
          set(r, c, '◇', C.cyanMid);
        } else {
          set(r, c, '·', C.cyanDark);
        }
      }
      // MIDDLE DECORATIVE RING
      else if (Math.abs(dist - MID_R) < 0.52) {
        const seg = Math.floor(angle / 5) % 3;
        if (seg === 0) {
          set(r, c, '─', C.cyanDim);
        } else if (seg === 1) {
          set(r, c, '·', C.cyanDark);
        } else {
          set(r, c, ' ', C.cyanDark);
        }
      }
      // INNER RING
      else if (Math.abs(dist - INNER_R) < 0.5) {
        set(r, c, '·', C.gray);
      }
    }
  }

  // Center text
  const topLabel = '── V.E.C.T.O.R. ──';
  const topRow = Math.round(CY) - 1;
  const topStart = Math.round(CX - topLabel.length / 2);
  [...topLabel].forEach((ch, i) => set(topRow, topStart + i, ch, C.cyanBright, true));

  const mainTitle = 'Virtual Entity for';
  const main2 = 'Cognitive Tasks and';
  const main3 = 'Operational Reasoning';
  const mRow = Math.round(CY);
  ([
    [mainTitle, mRow],
    [main2, mRow + 1],
    [main3, mRow + 2],
  ] as Array<[string, number]>).forEach(([txt, row]) => {
    const start = Math.round(CX - txt.length / 2);
    [...txt].forEach((ch, i) => set(row, start + i, ch, C.dimWhite));
  });

  const ver = '[ v0.1.0 ]';
  const verRow = Math.round(CY) + 4;
  const verStart = Math.round(CX - ver.length / 2);
  [...ver].forEach((ch, i) => set(verRow, verStart + i, ch, C.cyanDim));

  // Scanning indicator dot
  const scanAngle = (tick * 3) % 360;
  const scanR = Math.round(CY + (MID_R + 1.5) * Math.sin((scanAngle * Math.PI) / 180));
  const scanC = Math.round(CX + ((MID_R + 1.5) / ASPECT) * Math.cos((scanAngle * Math.PI) / 180));
  set(scanR, scanC, '◉', C.cyanBright, true);

  // Corner blueprint decorations
  const corners: Array<[number, number]> = [
    [0, 0], [0, 2], [1, 0],
    [0, COLS - 1], [0, COLS - 3], [1, COLS - 1],
    [GRID_ROWS - 1, 0], [GRID_ROWS - 2, 0], [GRID_ROWS - 1, 2],
    [GRID_ROWS - 1, COLS - 1], [GRID_ROWS - 2, COLS - 1], [GRID_ROWS - 1, COLS - 3],
  ];
  corners.forEach(([r, c]) => set(r, c, '┼', C.cyanDark));

  // Blueprint schematic lines
  for (let i = 3; i < 10; i++) {
    set(0, i, '─', C.cyanDark);
    set(0, COLS - 1 - i, '─', C.cyanDark);
    set(GRID_ROWS - 1, i, '─', C.cyanDark);
    set(GRID_ROWS - 1, COLS - 1 - i, '─', C.cyanDark);
  }
  for (let i = 2; i < 5; i++) {
    set(i, 0, '│', C.cyanDark);
    set(i, COLS - 1, '│', C.cyanDark);
    set(GRID_ROWS - 1 - i, 0, '│', C.cyanDark);
    set(GRID_ROWS - 1 - i, COLS - 1, '│', C.cyanDark);
  }

  // Small data readouts (blueprint feel)
  const topRight = `Cu:${(tick % 100).toString().padStart(2, '0')}`;
  const botLeft = `At:${((tick * 3) % 100).toString().padStart(2, '0')}`;
  const botRight = `No:${((tick * 7) % 100).toString().padStart(2, '0')}`;

  [...topRight].forEach((ch, i) => set(1, COLS - 10 + i, ch, C.gray));
  [...botLeft].forEach((ch, i) => set(GRID_ROWS - 2, 1 + i, ch, C.gray));
  [...botRight].forEach((ch, i) => set(GRID_ROWS - 2, COLS - 10 + i, ch, C.gray));

  return grid;
}

// ─── Row renderer ─────────────────────────────────────────────────────────────
function rowToString(row: Cell[]): string {
  return row
    .map((cell) => {
      if (cell.char === ' ') return ' ';
      let s = cell.char;
      try {
        s = chalk.hex(cell.color)(s);
        if (cell.bold) s = chalk.bold(s);
      } catch {
        /* no color */
      }
      return s;
    })
    .join('');
}

// ─── Status bar ───────────────────────────────────────────────────────────────
interface StatusBarProps {
  tick: number;
  model?: string;
  modelsOnline?: number;
  hasVectorMd?: boolean;
}

const StatusBar: React.FC<StatusBarProps> = ({
  tick,
  model = 'vector-focus',
  modelsOnline = 0,
  hasVectorMd = false,
}) => {
  const blink = tick % 16 < 10;

  return (
    <Box flexDirection="column" alignItems="center" marginTop={0}>
      <Text>{chalk.hex(C.cyanDark)('─'.repeat(COLS))}</Text>

      <Box flexDirection="row" gap={3} justifyContent="center">
        <Text>
          {chalk.hex(C.cyanDim)('Model')} {chalk.hex(C.cyan).bold(model)}
        </Text>
        <Text>{chalk.hex(C.gray)('·')}</Text>
        <Text>
          {chalk.hex(C.cyanDim)('Status')}{' '}
          {blink
            ? chalk.hex(C.green).bold('● online')
            : chalk.hex(C.cyanDark)('● online')}
        </Text>
        <Text>{chalk.hex(C.gray)('·')}</Text>
        <Text>
          {chalk.hex(C.white)(String(modelsOnline))} {chalk.hex(C.cyanDim)('models')}
        </Text>
      </Box>

      <Box flexDirection="row" gap={2} marginTop={0} justifyContent="center">
        {(
          [
            ['/help', 'list commands'],
            ['@<file>', 'attach files'],
            ['/sparc', 'run pipeline'],
            ['/quit', 'exit'],
          ] as Array<[string, string]>
        ).map(([cmd, desc]) => (
          <Text key={cmd}>
            {chalk.hex(C.cyan).bold(cmd)}
            {chalk.hex(C.gray)(` ${desc}`)}
          </Text>
        ))}
      </Box>

      <Text>{chalk.hex(C.cyanDark)('─'.repeat(COLS))}</Text>
      <Text>
        {hasVectorMd
          ? chalk.hex(C.green)('● VECTOR.md loaded')
          : chalk.hex(C.cyanDark)('○ No VECTOR.md  ·  /init')}
        {'  '}
        {chalk.hex(C.gray)('repl · ' + model)}
      </Text>
    </Box>
  );
};

// ─── Main HUD Component ───────────────────────────────────────────────────────
interface VectorHUDProps {
  model?: string;
  modelsOnline?: number;
  hasVectorMd?: boolean;
  /** Called on q / Esc — defaults to exit. Use to dismiss the splash. */
  onDismiss?: () => void;
  /** Disable animation (for static rendering, e.g. CI/testing) */
  static?: boolean;
}

const VectorHUD: React.FC<VectorHUDProps> = ({
  model = 'vector-focus',
  modelsOnline = 0,
  hasVectorMd = false,
  onDismiss,
  static: isStatic = false,
}) => {
  const [tick, setTick] = useState(0);
  const { exit } = useApp();

  useEffect(() => {
    if (isStatic) return;
    const anim = setInterval(() => setTick((t) => t + 1), 55);
    return () => clearInterval(anim);
  }, [isStatic]);

  useInput((input, key) => {
    if (input === 'q' || key.escape) {
      if (onDismiss) onDismiss();
      else exit();
    }
  });

  const grid = buildFrame(tick);

  return (
    <Box flexDirection="column" alignItems="center" paddingTop={1}>
      <Box flexDirection="column">
        {grid.map((row, ri) => (
          <Text key={ri}>{rowToString(row)}</Text>
        ))}
      </Box>
      <StatusBar tick={tick} model={model} modelsOnline={modelsOnline} hasVectorMd={hasVectorMd} />
    </Box>
  );
};

export default VectorHUD;
