/**
 * VectorCode TUI theme — colors, glyphs, layout constants.
 * Mirrors the Python CLI banner aesthetic for consistency.
 */
export declare const theme: {
    readonly brand: "cyanBright";
    readonly brandText: "whiteBright";
    readonly accent: "cyan";
    readonly dim: "gray";
    readonly success: "green";
    readonly warning: "yellow";
    readonly error: "red";
    readonly info: "blue";
    readonly active: "magenta";
    readonly user: "cyanBright";
    readonly assistant: "white";
    readonly tool: "magenta";
    readonly system: "gray";
    readonly bgPanel: undefined;
    readonly bgInput: undefined;
};
export declare const glyphs: {
    readonly mark: "⟨▶⟩";
    readonly online: "●";
    readonly offline: "○";
    readonly thinking: "◌";
    readonly done: "✓";
    readonly failed: "✗";
    readonly warn: "⚠";
    readonly arrow: "▸";
    readonly prompt: ">";
    readonly bullet: "•";
    readonly topLeft: "╭";
    readonly topRight: "╮";
    readonly bottomLeft: "╰";
    readonly bottomRight: "╯";
    readonly horizontal: "─";
    readonly vertical: "│";
    readonly toolStart: "●";
    readonly toolDone: "✓";
    readonly toolFail: "✗";
    readonly spinner: readonly ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
};
export declare const layout: {
    readonly paddingX: 2;
    readonly paddingY: 1;
    readonly topBarHeight: 1;
    readonly statusLineHeight: 1;
    readonly inputHeight: 3;
    readonly toolPaneWidthRatio: 0.35;
    readonly maxChatLines: 1000;
    readonly maxToolEvents: 200;
};
export declare const keys: {
    readonly cancelInput: "escape";
    readonly submitInput: "return";
    readonly togglePane: "tab";
    readonly scrollUp: "pageup";
    readonly scrollDown: "pagedown";
    readonly clearScreen: "ctrl+l";
    readonly quit: "ctrl+c";
};
