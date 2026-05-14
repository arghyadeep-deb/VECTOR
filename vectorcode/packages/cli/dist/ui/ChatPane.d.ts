/**
 * ChatPane — main conversation view.
 * Renders user/assistant/tool messages with smooth streaming + colors.
 */
import React from 'react';
import type { ChatMessage } from '../types.js';
interface ChatPaneProps {
    messages: ChatMessage[];
    thinking?: boolean;
    thinkingText?: string;
}
export declare const ChatPane: React.FC<ChatPaneProps>;
export {};
