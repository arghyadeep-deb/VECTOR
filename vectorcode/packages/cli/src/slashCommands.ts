/**
 * Slash command registry for autocomplete + dispatch.
 */

import type { SlashCommand } from './types.js';

export const SLASH_COMMANDS: SlashCommand[] = [
  // Session
  { name: 'help', description: 'show all commands', category: 'session' },
  { name: 'status', description: 'session info — model, mode, tokens, uptime', category: 'session' },
  { name: 'clear', description: 'clear conversation history', category: 'session' },
  { name: 'reset', description: 'reset session', category: 'session' },
  { name: 'quit', description: 'exit', category: 'session' },
  { name: 'save', description: 'save session to disk', category: 'session' },
  { name: 'restore', description: 'restore a saved session', category: 'session' },

  // Models
  { name: 'model', description: 'switch model: /model anthropic/claude-sonnet-4-5', category: 'models' },
  { name: 'models', description: 'list configured providers + reachability', category: 'models' },

  // Modes
  { name: 'mode', description: 'switch mode: cautious|standard|autonomous|read-only', category: 'modes' },

  // Memory + context
  { name: 'memory', description: 'show session memory', category: 'memory' },
  { name: 'compact', description: 'compact context', category: 'memory' },
  { name: 'cost', description: 'token usage + cost estimate', category: 'memory' },

  // Files
  { name: 'diff', description: 'show all file changes this session', category: 'files' },
  { name: 'commit', description: '/commit [msg] — commit changes', category: 'files' },
  { name: 'undo', description: 'revert last file write', category: 'files' },
  { name: 'init', description: 'generate VECTOR.md', category: 'files' },

  // Agents + skills
  { name: 'spawn', description: '/spawn <task> — spawn a worker subagent', category: 'agents' },
  { name: 'sparc', description: '/sparc <task> — run SPARC pipeline', category: 'agents' },
  { name: 'skills', description: 'list available skills', category: 'agents' },
  { name: 'tools', description: 'list registered tool categories', category: 'agents' },

  // Comms
  { name: 'notify', description: '/notify <text> — send via configured comms', category: 'comms' },
  { name: 'comms', description: 'comms status', category: 'comms' },

  // Web
  { name: 'search', description: '/search <query> — web search', category: 'web' },
  { name: 'fetch', description: '/fetch <url> — fetch + summarize URL', category: 'web' },

  // Analytics
  { name: 'usage', description: '/usage [days] — analytics', category: 'analytics' },
  { name: 'persona', description: '/persona <name> — switch personality', category: 'analytics' },
];
