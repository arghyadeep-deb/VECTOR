/**
 * StatusLine — bottom thin bar showing iteration usage, hints, hotkeys.
 */
import React from 'react';
interface StatusLineProps {
    iterationsUsed?: number;
    iterationsMax?: number;
    hint?: string;
    busy?: boolean;
}
export declare const StatusLine: React.FC<StatusLineProps>;
export {};
