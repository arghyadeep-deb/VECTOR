/**
 * TopBar — persistent header showing model, mode, gateway health, token usage.
 */
import React from 'react';
import type { SessionStatus } from '../types.js';
interface TopBarProps {
    status: Partial<SessionStatus>;
    gatewayHealthy: boolean;
}
export declare const TopBar: React.FC<TopBarProps>;
export {};
