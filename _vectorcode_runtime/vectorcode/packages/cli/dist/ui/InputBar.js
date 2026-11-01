import React, { useState, useRef, useMemo, useEffect } from 'react';
import { Box, Text, useInput, useStdout } from 'ink';
import stringWidth from 'string-width';
import stripAnsi from 'strip-ansi';
import { theme } from './theme.js';
export function InputBar({ onSubmit, busy = false, disabled = false, slashCommands, modelLabel, modeLabel, onMenuChange, insertion, history, onDraftChange, attachmentLabel }) {
    const [editor, setEditor] = useState({ value: '', cursor: 0 });
    const current = useRef(editor);
    // null = live draft (not browsing history); otherwise an index into `history`.
    // Up/Down only browse history when the draft has no newline, so multi-line
    // drafts keep today's behavior (no vertical cursor movement either way).
    const historyIndex = useRef(null);
    const draftBeforeHistory = useRef({ value: '', cursor: 0 });
    const { stdout } = useStdout();
    const width = Math.max(10, (stdout.columns || 100) - 8);
    const [selected, setSelected] = useState(0);
    const [dismissed, setDismissed] = useState(null);
    const suggestions = useMemo(() => editor.value.startsWith('/') && !/\s/.test(editor.value)
        && !disabled && dismissed !== editor.value
        ? slashCommands.filter(command => command.name.startsWith(editor.value.slice(1).toLowerCase()))
            .sort((a, b) => Number(b.name === editor.value.slice(1).toLowerCase()) -
            Number(a.name === editor.value.slice(1).toLowerCase())) : [], [editor.value, disabled, dismissed, slashCommands]);
    const active = Math.min(selected, Math.max(0, suggestions.length - 1));
    useEffect(() => { onMenuChange?.({ items: suggestions, selected: active }); }, [suggestions, active, onMenuChange]);
    const update = (value, cursor, fromHistory = false) => {
        setSelected(0);
        setDismissed(null);
        if (!fromHistory)
            historyIndex.current = null;
        current.current = { value, cursor };
        setEditor(current.current);
        onDraftChange?.(value);
    };
    useEffect(() => {
        if (!insertion)
            return;
        const { value, cursor } = current.current;
        const chars = Array.from(value);
        const text = stripAnsi(insertion.text).replace(/\r\n?/g, '\n').replace(/[\x00-\x08\x0b-\x1f\x7f]/g, '');
        chars.splice(cursor, 0, text);
        update(chars.join(''), cursor + Array.from(text).length);
    }, [insertion]);
    const submitDraft = (value) => {
        const result = onSubmit(value);
        if (result === false)
            return;
        const next = typeof result === 'string' ? result : '';
        update(next, Array.from(next).length);
    };
    useInput((input, key) => {
        if (disabled || key.pageUp || key.pageDown)
            return;
        if (suggestions.length) {
            if (key.upArrow) {
                setSelected((active + suggestions.length - 1) % suggestions.length);
                return;
            }
            if (key.downArrow) {
                setSelected((active + 1) % suggestions.length);
                return;
            }
            if (key.escape) {
                setDismissed(current.current.value);
                return;
            }
            if (key.tab || (key.return && !key.meta && !key.shift && !busy)) {
                const command = suggestions[active];
                const completed = '/' + command.name + (command.takesArgument ? ' ' : '');
                if (key.tab || command.takesArgument) {
                    update(completed, completed.length);
                    setDismissed(completed);
                }
                else
                    submitDraft(completed);
                return;
            }
        }
        if (key.tab || key.escape)
            return;
        if ((key.upArrow || key.downArrow) && history?.length && !current.current.value.includes('\n')) {
            if (key.upArrow) {
                if (historyIndex.current === null)
                    draftBeforeHistory.current = current.current;
                const next = historyIndex.current === null ? history.length - 1 : historyIndex.current - 1;
                if (next < 0)
                    return;
                historyIndex.current = next;
                update(history[next], history[next].length, true);
            }
            else {
                if (historyIndex.current === null)
                    return;
                const next = historyIndex.current + 1;
                if (next >= history.length) {
                    historyIndex.current = null;
                    update(draftBeforeHistory.current.value, draftBeforeHistory.current.cursor, true);
                }
                else {
                    historyIndex.current = next;
                    update(history[next], history[next].length, true);
                }
            }
            return;
        }
        if (key.upArrow || key.downArrow)
            return;
        const { value, cursor } = current.current;
        const characters = Array.from(value);
        if (key.ctrl) {
            if (input === 'a')
                update(value, 0);
            if (input === 'e')
                update(value, characters.length);
            if (input === 'u')
                update('', 0);
            return;
        }
        if (key.return && !key.meta && !key.shift) {
            if ((!busy || ['/stop', '/quit', '/q'].includes(value.trim())) && value.trim()) {
                submitDraft(value);
            }
            return;
        }
        if (key.leftArrow) {
            update(value, Math.max(0, cursor - 1));
            return;
        }
        if (key.rightArrow) {
            update(value, Math.min(characters.length, cursor + 1));
            return;
        }
        if (key.backspace || key.delete) {
            if (key.delete) {
                characters.splice(cursor, 1);
                update(characters.join(''), cursor);
            }
            else if (cursor) {
                characters.splice(cursor - 1, 1);
                update(characters.join(''), cursor - 1);
            }
            return;
        }
        const inserted = key.return || input === '\r' ? '\n'
            : stripAnsi(input).replace(/\r\n?/g, '\n').replace(/\t/g, '  ').replace(/[\x00-\x08\x0b-\x1f\x7f]/g, '');
        characters.splice(cursor, 0, inserted);
        update(characters.join(''), cursor + Array.from(inserted).length);
    });
    const rows = [{ text: '', cursor: null }];
    let used = 0;
    for (const [index, character] of [...Array.from(editor.value), ' '].entries()) {
        if (character === '\n' && index === editor.cursor) {
            rows[rows.length - 1].cursor = rows[rows.length - 1].text.length;
            rows[rows.length - 1].text += ' ';
        }
        if (character === '\n' || used + stringWidth(character) > width) {
            rows.push({ text: '', cursor: null });
            used = 0;
            if (character === '\n')
                continue;
        }
        const row = rows[rows.length - 1];
        if (index === editor.cursor)
            row.cursor = row.text.length;
        row.text += character;
        used += stringWidth(character);
    }
    const cursorRow = rows.findIndex(row => row.cursor !== null);
    const visible = rows.slice(Math.max(0, cursorRow - 1), Math.max(2, cursorRow + 1));
    return React.createElement(Box, { paddingX: 1, height: 8, flexDirection: "column" },
        attachmentLabel ? React.createElement(Box, { height: 2, flexDirection: "column", overflow: "hidden" },
            React.createElement(Text, { color: theme.dim, wrap: "truncate-middle" }, attachmentLabel.location),
            React.createElement(Box, { justifyContent: "space-between" },
                React.createElement(Text, { color: theme.dim }, attachmentLabel.size),
                React.createElement(Text, { color: theme.brand }, "Ctrl+D detach"))) : React.createElement(Box, { height: 1 },
            React.createElement(Text, { color: theme.dim }, suggestions.length ? '\u2191 \u2193 choose \u00b7 Enter select \u00b7 Tab complete \u00b7 Esc close' : '')),
        React.createElement(Box, { borderStyle: "round", borderColor: busy ? theme.warning : theme.border, flexDirection: "column", paddingX: 1, height: 6 },
            React.createElement(Box, { height: 2, flexDirection: "column", overflow: "hidden" }, !editor.value ? React.createElement(Text, { color: theme.dim },
                React.createElement(Text, { color: theme.brand }, "\u203A "),
                busy ? 'Draft your next message…' : 'Ask VectorCode to work on your project…')
                : visible.map((row, index) => {
                    const active = row.cursor === null ? '' : Array.from(row.text.slice(row.cursor))[0] || ' ';
                    return React.createElement(Text, { key: index, wrap: "truncate-end" },
                        React.createElement(Text, { color: theme.brand }, index ? '  ' : '› '),
                        row.cursor === null || disabled ? row.text : React.createElement(React.Fragment, null,
                            row.text.slice(0, row.cursor),
                            React.createElement(Text, { inverse: true }, active),
                            row.text.slice(row.cursor + active.length)));
                })),
            React.createElement(Box, { marginTop: 1, justifyContent: "space-between", overflow: "hidden" },
                React.createElement(Box, { flexGrow: 1, flexShrink: 1 },
                    React.createElement(Text, { color: theme.accent, wrap: "truncate-middle" }, modelLabel)),
                React.createElement(Text, { color: theme.active }, modeLabel))));
}
//# sourceMappingURL=InputBar.js.map