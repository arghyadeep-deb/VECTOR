/**
 * VectorCode TUI theme — colors, glyphs, layout constants.
 * Mirrors the Python CLI banner aesthetic for consistency.
 */
export const theme = {
    // Brand
    brand: 'cyanBright',
    brandText: 'whiteBright',
    accent: 'cyan',
    dim: 'gray',
    // States
    success: 'green',
    warning: 'yellow',
    error: 'red',
    info: 'blue',
    active: 'magenta',
    // Roles
    user: 'cyanBright',
    assistant: 'white',
    tool: 'magenta',
    system: 'gray',
    // Backgrounds
    bgPanel: undefined,
    bgInput: undefined,
};
export const glyphs = {
    // Logo mark (matches Python banner)
    mark: '⟨▶⟩',
    // Status indicators
    online: '●',
    offline: '○',
    thinking: '◌',
    done: '✓',
    failed: '✗',
    warn: '⚠',
    arrow: '▸',
    prompt: '>',
    bullet: '•',
    // Box drawing (rounded)
    topLeft: '╭',
    topRight: '╮',
    bottomLeft: '╰',
    bottomRight: '╯',
    horizontal: '─',
    vertical: '│',
    // Tool execution
    toolStart: '●',
    toolDone: '✓',
    toolFail: '✗',
    // Spinner frames (smooth)
    spinner: ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'],
};
export const layout = {
    paddingX: 2,
    paddingY: 1,
    topBarHeight: 1,
    statusLineHeight: 1,
    inputHeight: 3,
    toolPaneWidthRatio: 0.35,
    maxChatLines: 1000,
    maxToolEvents: 200,
};
export const keys = {
    cancelInput: 'escape',
    submitInput: 'return',
    togglePane: 'tab',
    scrollUp: 'pageup',
    scrollDown: 'pagedown',
    clearScreen: 'ctrl+l',
    quit: 'ctrl+c',
};
//# sourceMappingURL=theme.js.map