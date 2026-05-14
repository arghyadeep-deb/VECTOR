/**
 * Welcome banner — JARVIS arc reactor with VECTOR core + status block.
 */
import React from 'react';
interface BannerProps {
    version?: string;
    model?: string;
    modelsOnline?: number;
    hasVectorMd?: boolean;
}
export declare const Banner: React.FC<BannerProps>;
export {};
