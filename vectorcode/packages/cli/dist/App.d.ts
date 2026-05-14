/**
 * Main App component — top-level state, routing, and pane orchestration.
 */
import React from 'react';
import type { SessionStatus } from './types.js';
interface AppProps {
    gatewayUrl: string;
    initialModel?: string;
    initialMode?: SessionStatus['mode'];
    showBanner?: boolean;
    /** Show the animated JARVIS HUD splash on launch */
    showHud?: boolean;
}
export declare const App: React.FC<AppProps>;
export {};
