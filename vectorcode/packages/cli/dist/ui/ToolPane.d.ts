/**
 * ToolPane — right side panel showing tool execution timeline + active sessions.
 */
import React from 'react';
import type { ToolEvent } from '../types.js';
interface ToolPaneProps {
    events: ToolEvent[];
    width?: number;
}
export declare const ToolPane: React.FC<ToolPaneProps>;
export {};
