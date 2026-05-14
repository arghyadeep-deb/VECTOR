/**
 * Banner — circular reactor + status panel, Claude Code style.
 */
import React from 'react';
interface BannerProps {
    cwd?: string;
    model?: string;
    modelsOnline?: number;
}
export declare const Banner: React.FC<BannerProps>;
export {};
