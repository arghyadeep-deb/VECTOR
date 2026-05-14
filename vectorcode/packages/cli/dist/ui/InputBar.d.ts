/**
 * InputBar — user input with slash command autocomplete.
 */
import React from 'react';
import type { SlashCommand } from '../types.js';
interface InputBarProps {
    onSubmit: (value: string) => void;
    onCancel?: () => void;
    busy?: boolean;
    placeholder?: string;
    slashCommands: SlashCommand[];
    modelLabel?: string;
    modeLabel?: string;
}
export declare const InputBar: React.FC<InputBarProps>;
export {};
