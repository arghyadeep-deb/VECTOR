export const theme = {
    brand: '#9ee6bf', brandText: '#ecedef', accent: '#9ee6bf', dim: '#858b94',
    success: '#9ee6bf', warning: '#e5bd7a', error: '#f38b8b', info: '#90b9dc', active: '#c7adf3',
    user: '#c7adf3', assistant: '#ecedef', tool: '#90b9dc', system: '#858b94',
    bgPanel: '#17191d', bgInput: '#22252b', border: '#3a3f47',
};
export function applySkin(colors) {
    const mapping = { brand: 'ui_accent', accent: 'ui_accent', brandText: 'banner_text',
        dim: 'banner_dim', border: 'input_rule', success: 'ui_ok', warning: 'ui_warn', error: 'ui_error',
        user: 'ui_label', assistant: 'banner_text', system: 'banner_dim', tool: 'ui_accent' };
    for (const [target, source] of Object.entries(mapping)) {
        if (/^#[0-9a-f]{6}$/i.test(colors[source] || ''))
            theme[target] = colors[source];
    }
}
export const glyphs = {
    mark: '◆', online: '●', offline: '○', thinking: '◌', done: '✓', failed: '×', warn: '!',
    arrow: '›', prompt: '›', bullet: '·', toolStart: '◌', toolDone: '✓', toolFail: '×',
};
//# sourceMappingURL=theme.js.map