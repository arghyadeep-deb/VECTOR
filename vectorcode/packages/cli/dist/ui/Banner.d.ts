/**
 * Welcome banner — VectorCode ⟨▶⟩ mark, version, tips.
 * Mirrors the Python CLI banner aesthetic.
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
