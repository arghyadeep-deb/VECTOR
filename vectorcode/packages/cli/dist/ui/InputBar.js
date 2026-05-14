/**
 * InputBar — user input with slash command autocomplete.
 */
import React, { useState, useMemo } from 'react';
import { Box, Text, useInput } from 'ink';
import TextInput from 'ink-text-input';
import { theme, glyphs } from './theme.js';
export const InputBar = ({ onSubmit, onCancel, busy = false, placeholder = 'Type a task or /help', slashCommands, modelLabel = 'vector', modeLabel = 'repl', }) => {
    const [value, setValue] = useState('');
    // Slash autocomplete suggestions
    const suggestions = useMemo(() => {
        if (!value.startsWith('/'))
            return [];
        const q = value.slice(1).toLowerCase();
        return slashCommands
            .filter((c) => c.name.toLowerCase().startsWith(q))
            .slice(0, 6);
    }, [value, slashCommands]);
    useInput((input, key) => {
        if (key.escape && onCancel) {
            onCancel();
        }
    });
    const handleSubmit = (v) => {
        if (!v.trim() || busy)
            return;
        onSubmit(v.trim());
        setValue('');
    };
    return (React.createElement(Box, { flexDirection: "column", paddingX: 1 },
        suggestions.length > 0 && (React.createElement(Box, { flexDirection: "column", marginBottom: 1 }, suggestions.map((c) => (React.createElement(Box, { key: c.name },
            React.createElement(Text, { color: theme.accent }, ('/' + c.name).padEnd(20)),
            React.createElement(Text, { color: theme.dim }, c.description)))))),
        React.createElement(Box, null,
            React.createElement(Text, { color: theme.dim },
                modeLabel,
                " \u00B7 ",
                modelLabel)),
        React.createElement(Box, null,
            React.createElement(Text, { color: theme.brand, bold: true },
                glyphs.prompt,
                ' '),
            busy ? (React.createElement(Text, { color: theme.dim }, value || placeholder)) : (React.createElement(TextInput, { value: value, onChange: setValue, onSubmit: handleSubmit, placeholder: placeholder })))));
};
//# sourceMappingURL=InputBar.js.map