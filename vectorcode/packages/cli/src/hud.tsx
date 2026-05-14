#!/usr/bin/env node
/**
 * VectorCode HUD — standalone splash renderer.
 *
 * Use case: just show the JARVIS HUD (no chat, no gateway).
 * Useful for: demos, screenshots, splash screen on `vector` start.
 *
 * Run:
 *   node dist/hud.js              full animated HUD
 *   vector-hud                    (after install)
 */

import React from 'react';
import { render } from 'ink';
import VectorHUD from './ui/VectorHUD.js';

render(React.createElement(VectorHUD));
