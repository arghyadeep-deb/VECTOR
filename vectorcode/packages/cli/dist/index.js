#!/usr/bin/env node
/**
 * VectorCode TUI — entry point.
 *
 * Usage:
 *   vector-tui                          start TUI against http://127.0.0.1:8123
 *   vector-tui --gateway URL            point at a different gateway
 *   vector-tui --model anthropic/...    set initial model
 *   vector-tui --mode autonomous        set initial mode
 *   vector-tui --no-banner              skip welcome banner
 */
import React from 'react';
import { render } from 'ink';
import { Command } from 'commander';
import { App } from './App.js';
const program = new Command();
program
    .name('vector-tui')
    .description('VectorCode terminal UI')
    .version('0.1.0')
    .option('-g, --gateway <url>', 'Gateway base URL', 'http://127.0.0.1:8123')
    .option('-m, --model <id>', 'Initial model (e.g. anthropic/claude-sonnet-4-5)', 'vector-focus')
    .option('--mode <mode>', 'Initial mode (cautious|standard|autonomous|read-only)', 'standard')
    .option('--no-banner', 'Skip welcome banner')
    .option('--no-hud', 'Skip JARVIS HUD splash on launch')
    .parse(process.argv);
const opts = program.opts();
const validModes = [
    'cautious',
    'standard',
    'autonomous',
    'read-only',
    'repl',
];
const mode = (validModes.includes(opts.mode) ? opts.mode : 'standard');
render(React.createElement(App, {
    gatewayUrl: opts.gateway,
    initialModel: opts.model,
    initialMode: mode,
    showBanner: opts.banner !== false,
    showHud: opts.hud !== false,
}));
//# sourceMappingURL=index.js.map