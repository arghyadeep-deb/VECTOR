#!/usr/bin/env node
import React from 'react';
import { render } from 'ink';
import { Command } from 'commander';
import { App } from './App.js';
import { terminalInput } from './terminalInput.js';
const options = new Command().name('vector tui').description('VectorCode full-screen local coding workspace')
    .option('-m, --model <id>', 'Model ID', 'vector-focus')
    .option('--mode <mode>', 'cautious, standard or read-only', 'standard')
    .option('--python <path>', 'Python executable', process.env.VECTOR_PYTHON || 'python')
    .option('--editor-context-file <path>', 'Explicit editor envelope to review before submitting')
    .option('--resume [session]', 'Resume latest project conversation or a session ID prefix')
    .parse().opts();
if (!process.stdin.isTTY || !process.stdout.isTTY) {
    process.stderr.write('The full-screen UI needs an interactive terminal. Use vector run for pipes or scripts.\n');
    process.exit(1);
}
if (!['cautious', 'standard', 'read-only'].includes(options.mode)) {
    process.stderr.write('Unsupported UI mode. Use cautious, standard or read-only.\n');
    process.exit(1);
}
process.stdout.write('\x1b[?1049h');
let restored = false;
const restore = () => { if (!restored) {
    process.stdout.write('\x1b[?1049l');
    restored = true;
} };
process.once('exit', restore);
const keyboard = terminalInput(process.stdin);
const app = render(React.createElement(App, { initialModel: options.model, initialMode: options.mode, python: options.python, editorContextFile: options.editorContextFile, resumeSession: options.resume === true ? 'latest' : options.resume }), { exitOnCtrlC: false, stdin: keyboard.input });
const finish = () => { keyboard.close(); restore(); };
app.waitUntilExit().then(finish, finish);
//# sourceMappingURL=index.js.map