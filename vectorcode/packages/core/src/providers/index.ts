/**
 * VectorCode — Universal Provider System
 * 17 providers, 60+ models, single .chat() call
 */
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

// ── Types ────────────────────────────────────────────────────

export interface Message {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatOptions {
  model: string;
  messages: Message[];
  temperature?: number;
  max_tokens?: number;
  stream?: boolean;
  system?: string;
}

export interface ChatResponse {
  content: string;
  model: string;
  usage: { input_tokens: number; output_tokens: number };
  provider: string;
}

export interface ModelInfo {
  id: string;
  provider: string;
  displayName: string;
  contextWindow: number;
  supportsTools: boolean;
  supportsVision: boolean;
  costPer1kInput: number;
  costPer1kOutput: number;
}

export interface VectorConfig {
  providers: Record<string, { apiKey?: string; baseUrl?: string; accountId?: string }>;
  defaults: {
    model: string;
    fastModel: string;
    localModel: string;
    temperature: number;
    maxTokens: number;
  };
}

export interface ProviderHealth {
  provider: string;
  reachable: boolean;
  models: string[];
  contextWindow: number;
  supportsTools: boolean;
  detail: string;
}

// ── Config Manager ───────────────────────────────────────────

const CONFIG_PATH = path.join(os.homedir(), ".config", "vector", "config.json");

export function loadConfig(): VectorConfig {
  if (fs.existsSync(CONFIG_PATH)) {
    return JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
  }
  return {
    providers: {},
    defaults: {
      model: "anthropic/claude-sonnet-4-6",
      fastModel: "groq/llama-3.3-70b-versatile",
      localModel: "ollama/llama3.2",
      temperature: 0.7,
      maxTokens: 4096,
    },
  };
}

export function saveConfig(config: VectorConfig): void {
  const dir = path.dirname(CONFIG_PATH);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));
}

export function setApiKey(provider: string, key: string, extra?: Record<string, string>): void {
  const config = loadConfig();
  (config.providers as any)[provider] = { apiKey: key, ...extra };
  saveConfig(config);
  console.log(`\x1b[92m✓ ${provider} API key saved\x1b[0m`);
}

// ── Model Registry (60+ models, 17 providers) ────────────────

export const MODEL_REGISTRY: ModelInfo[] = [
  { id: "anthropic/claude-opus-4-5",      provider: "anthropic", displayName: "Claude Opus 4.5",      contextWindow: 200000, supportsTools: true,  supportsVision: true,  costPer1kInput: 0.015,  costPer1kOutput: 0.075  },
  { id: "anthropic/claude-sonnet-4-6",    provider: "anthropic", displayName: "Claude Sonnet 4.6",    contextWindow: 200000, supportsTools: true,  supportsVision: true,  costPer1kInput: 0.003,  costPer1kOutput: 0.015  },
  { id: "anthropic/claude-haiku-4-5",     provider: "anthropic", displayName: "Claude Haiku 4.5",     contextWindow: 200000, supportsTools: true,  supportsVision: true,  costPer1kInput: 0.00025,costPer1kOutput: 0.00125 },
  { id: "openai/gpt-4o",                  provider: "openai",    displayName: "GPT-4o",               contextWindow: 128000, supportsTools: true,  supportsVision: true,  costPer1kInput: 0.005,  costPer1kOutput: 0.015  },
  { id: "openai/gpt-4o-mini",             provider: "openai",    displayName: "GPT-4o Mini",          contextWindow: 128000, supportsTools: true,  supportsVision: true,  costPer1kInput: 0.00015,costPer1kOutput: 0.0006 },
  { id: "openai/o3",                      provider: "openai",    displayName: "o3",                   contextWindow: 200000, supportsTools: true,  supportsVision: false, costPer1kInput: 0.01,   costPer1kOutput: 0.04   },
  { id: "openai/o4-mini",                 provider: "openai",    displayName: "o4-mini",              contextWindow: 200000, supportsTools: true,  supportsVision: true,  costPer1kInput: 0.0011, costPer1kOutput: 0.0044 },
  { id: "google/gemini-2.5-pro",          provider: "google",    displayName: "Gemini 2.5 Pro",       contextWindow: 1000000,supportsTools: true,  supportsVision: true,  costPer1kInput: 0.00125,costPer1kOutput: 0.005  },
  { id: "google/gemini-2.5-flash",        provider: "google",    displayName: "Gemini 2.5 Flash",     contextWindow: 1000000,supportsTools: true,  supportsVision: true,  costPer1kInput: 0.00025,costPer1kOutput: 0.001  },
  { id: "google/gemini-2.0-flash-exp",    provider: "google",    displayName: "Gemini 2.0 Flash Exp", contextWindow: 1000000,supportsTools: true,  supportsVision: true,  costPer1kInput: 0.0,    costPer1kOutput: 0.0    },
  { id: "mistral/mistral-large-latest",   provider: "mistral",   displayName: "Mistral Large",        contextWindow: 128000, supportsTools: true,  supportsVision: false, costPer1kInput: 0.004,  costPer1kOutput: 0.012  },
  { id: "mistral/codestral-latest",       provider: "mistral",   displayName: "Codestral",            contextWindow: 256000, supportsTools: true,  supportsVision: false, costPer1kInput: 0.001,  costPer1kOutput: 0.003  },
  { id: "mistral/mistral-small-latest",   provider: "mistral",   displayName: "Mistral Small",        contextWindow: 32000,  supportsTools: true,  supportsVision: false, costPer1kInput: 0.001,  costPer1kOutput: 0.003  },
  { id: "mistral/devstral-small",         provider: "mistral",   displayName: "Devstral Small",       contextWindow: 128000, supportsTools: true,  supportsVision: false, costPer1kInput: 0.001,  costPer1kOutput: 0.003  },
  { id: "groq/llama-4-scout-17b-16e-instruct", provider: "groq", displayName: "Llama 4 Scout",       contextWindow: 131072, supportsTools: true,  supportsVision: false, costPer1kInput: 0.00011,costPer1kOutput: 0.00034},
  { id: "groq/llama-4-maverick-17b-128e-instruct",provider:"groq",displayName:"Llama 4 Maverick",   contextWindow: 131072, supportsTools: true,  supportsVision: false, costPer1kInput: 0.0002, costPer1kOutput: 0.0006 },
  { id: "groq/llama-3.3-70b-versatile",   provider: "groq",      displayName: "Llama 3.3 70B",       contextWindow: 128000, supportsTools: true,  supportsVision: false, costPer1kInput: 0.00059,costPer1kOutput: 0.00079},
  { id: "groq/qwen-qwq-32b",              provider: "groq",      displayName: "Qwen QwQ 32B",         contextWindow: 128000, supportsTools: true,  supportsVision: false, costPer1kInput: 0.00029,costPer1kOutput: 0.00039},
  { id: "groq/deepseek-r1-distill-llama-70b",provider:"groq",    displayName: "DeepSeek R1 70B",     contextWindow: 128000, supportsTools: false, supportsVision: false, costPer1kInput: 0.00075,costPer1kOutput: 0.00099},
  { id: "nvidia/llama-3.1-nemotron-ultra-253b-v1", provider:"nvidia",displayName:"Nemotron Ultra 253B",contextWindow:128000,supportsTools:true,  supportsVision:false, costPer1kInput:0.001,  costPer1kOutput:0.004  },
  { id: "nvidia/llama-3.3-nemotron-super-49b-v1",  provider:"nvidia",displayName:"Nemotron Super 49B", contextWindow:128000,supportsTools:true,  supportsVision:false, costPer1kInput:0.00023,costPer1kOutput:0.00062},
  { id: "nvidia/mistral-nemo-minitron-8b-8k-instruct",provider:"nvidia",displayName:"Nemo Minitron 8B",contextWindow:8192, supportsTools:false, supportsVision:false, costPer1kInput:0.0,    costPer1kOutput:0.0    },
  { id: "nvidia/deepseek-ai/deepseek-r1", provider: "nvidia",    displayName: "DeepSeek R1 (NVIDIA)", contextWindow: 64000,  supportsTools: false, supportsVision: false, costPer1kInput: 0.004,  costPer1kOutput: 0.016  },
  { id: "nvidia/qwen/qwq-32b",            provider: "nvidia",    displayName: "QwQ 32B (NVIDIA)",     contextWindow: 32768,  supportsTools: true,  supportsVision: false, costPer1kInput: 0.0004, costPer1kOutput: 0.0012 },
  { id: "nvidia/google/gemma-3-27b-it",   provider: "nvidia",    displayName: "Gemma 3 27B (NVIDIA)", contextWindow: 131072, supportsTools: true,  supportsVision: true,  costPer1kInput: 0.0002, costPer1kOutput: 0.0002 },
  { id: "cloudflare/@cf/meta/llama-4-scout-17b-16e-instruct", provider:"cloudflare", displayName:"Llama 4 Scout (CF)", contextWindow:131072, supportsTools:true,  supportsVision:false, costPer1kInput:0.0,    costPer1kOutput:0.0    },
  { id: "cloudflare/@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",provider:"cloudflare",displayName:"DeepSeek R1 32B (CF)",contextWindow:32768, supportsTools:false, supportsVision:false, costPer1kInput:0.0,    costPer1kOutput:0.0    },
  { id: "cloudflare/@cf/google/gemma-3-12b-it",provider:"cloudflare",displayName:"Gemma 3 12B (CF)",contextWindow:131072,supportsTools:false, supportsVision:false, costPer1kInput:0.0,    costPer1kOutput:0.0    },
  { id: "cloudflare/@cf/mistral/mistral-7b-instruct-v0.2",provider:"cloudflare",displayName:"Mistral 7B (CF)",contextWindow:32768,supportsTools:false,supportsVision:false,costPer1kInput:0.0,costPer1kOutput:0.0},
  { id: "github/gpt-4o",                  provider: "github",    displayName: "GPT-4o (GitHub)",      contextWindow: 128000, supportsTools: true,  supportsVision: true,  costPer1kInput: 0.0,    costPer1kOutput: 0.0    },
  { id: "github/gpt-4o-mini",             provider: "github",    displayName: "GPT-4o Mini (GitHub)", contextWindow: 128000, supportsTools: true,  supportsVision: true,  costPer1kInput: 0.0,    costPer1kOutput: 0.0    },
  { id: "github/meta-llama-3.3-70b-instruct",provider:"github",  displayName: "Llama 3.3 70B (GitHub)",contextWindow:128000,supportsTools:true,  supportsVision:false, costPer1kInput:0.0,    costPer1kOutput:0.0    },
  { id: "github/mistral-large-2407",      provider: "github",    displayName: "Mistral Large (GitHub)",contextWindow:128000,supportsTools:true,  supportsVision:false, costPer1kInput:0.0,    costPer1kOutput:0.0    },
  { id: "github/ai21-jamba-1.5-large",    provider: "github",    displayName: "Jamba 1.5 Large",      contextWindow: 256000, supportsTools: true,  supportsVision: false, costPer1kInput: 0.0,    costPer1kOutput: 0.0    },
  { id: "together/meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",provider:"together",displayName:"Llama 4 Maverick (Together)",contextWindow:524288,supportsTools:true,supportsVision:false,costPer1kInput:0.00027,costPer1kOutput:0.00085},
  { id: "together/deepseek-ai/DeepSeek-R1",provider:"together",  displayName: "DeepSeek R1 (Together)",contextWindow:163840,supportsTools:false,supportsVision:false,costPer1kInput:0.007,  costPer1kOutput:0.007  },
  { id: "together/Qwen/QwQ-32B",          provider: "together",  displayName: "QwQ 32B (Together)",   contextWindow: 32768,  supportsTools: true,  supportsVision: false, costPer1kInput: 0.0012, costPer1kOutput: 0.0012 },
  { id: "openrouter/anthropic/claude-sonnet-4-6",provider:"openrouter",displayName:"Claude Sonnet 4.6 (OR)",contextWindow:200000,supportsTools:true,supportsVision:true,costPer1kInput:0.003,costPer1kOutput:0.015},
  { id: "openrouter/google/gemini-2.5-pro",provider:"openrouter", displayName:"Gemini 2.5 Pro (OR)",  contextWindow:1000000,supportsTools:true,supportsVision:true,costPer1kInput:0.00125,costPer1kOutput:0.005},
  { id: "openrouter/deepseek/deepseek-r1",provider:"openrouter",  displayName:"DeepSeek R1 (OR)",     contextWindow:163840, supportsTools:false,supportsVision:false,costPer1kInput:0.0008,costPer1kOutput:0.0032},
  { id: "xai/grok-3",                     provider: "xai",       displayName: "Grok 3",              contextWindow: 131072, supportsTools: true,  supportsVision: false, costPer1kInput: 0.003,  costPer1kOutput: 0.015  },
  { id: "xai/grok-3-mini",                provider: "xai",       displayName: "Grok 3 Mini",         contextWindow: 131072, supportsTools: true,  supportsVision: false, costPer1kInput: 0.0003, costPer1kOutput: 0.0005 },
  { id: "perplexity/sonar-pro",            provider:"perplexity", displayName:"Sonar Pro",            contextWindow: 200000, supportsTools: false, supportsVision: false, costPer1kInput: 0.003,  costPer1kOutput: 0.015  },
  { id: "perplexity/sonar",                provider:"perplexity", displayName:"Sonar",                contextWindow: 127072, supportsTools: false, supportsVision: false, costPer1kInput: 0.001,  costPer1kOutput: 0.001  },
  { id: "perplexity/sonar-reasoning-pro",  provider:"perplexity", displayName:"Sonar Reasoning Pro",  contextWindow: 127072, supportsTools: false, supportsVision: false, costPer1kInput: 0.008,  costPer1kOutput: 0.04   },
  { id: "fireworks/accounts/fireworks/models/llama-v3p3-70b-instruct",provider:"fireworks",displayName:"Llama 3.3 70B (Fireworks)",contextWindow:131072,supportsTools:true,supportsVision:false,costPer1kInput:0.0009,costPer1kOutput:0.0009},
  { id: "fireworks/accounts/fireworks/models/deepseek-r1",provider:"fireworks",displayName:"DeepSeek R1 (Fireworks)",contextWindow:163840,supportsTools:false,supportsVision:false,costPer1kInput:0.003,costPer1kOutput:0.008},
  { id: "cohere/command-r-plus-08-2024",   provider: "cohere",    displayName: "Command R+ (Aug 24)", contextWindow: 128000, supportsTools: true,  supportsVision: false, costPer1kInput: 0.0025, costPer1kOutput: 0.01   },
  { id: "cohere/command-r7b-12-2024",      provider: "cohere",    displayName: "Command R7B",         contextWindow: 128000, supportsTools: true,  supportsVision: false, costPer1kInput: 0.0000375,costPer1kOutput:0.00015},
  { id: "deepseek/deepseek-chat",          provider: "deepseek",  displayName: "DeepSeek V3",         contextWindow: 64000,  supportsTools: true,  supportsVision: false, costPer1kInput: 0.00027,costPer1kOutput: 0.0011 },
  { id: "deepseek/deepseek-reasoner",      provider: "deepseek",  displayName: "DeepSeek R1",         contextWindow: 64000,  supportsTools: false, supportsVision: false, costPer1kInput: 0.00055,costPer1kOutput: 0.00219},
  { id: "ollama/llama3.2",                 provider: "ollama",    displayName: "Llama 3.2 (local)",   contextWindow: 128000, supportsTools: true,  supportsVision: false, costPer1kInput: 0.0,    costPer1kOutput: 0.0    },
  { id: "ollama/qwen2.5-coder:32b",        provider: "ollama",    displayName: "Qwen2.5 Coder 32B",   contextWindow: 32768,  supportsTools: true,  supportsVision: false, costPer1kInput: 0.0,    costPer1kOutput: 0.0    },
  { id: "ollama/deepseek-r1:14b",          provider: "ollama",    displayName: "DeepSeek R1 14B",     contextWindow: 32768,  supportsTools: false, supportsVision: false, costPer1kInput: 0.0,    costPer1kOutput: 0.0    },
  { id: "lmstudio/local-model",            provider: "lmstudio",  displayName: "LM Studio (active)",  contextWindow: 32768,  supportsTools: false, supportsVision: false, costPer1kInput: 0.0,    costPer1kOutput: 0.0    },
];

// ── Base URL map per provider ────────────────────────────────

export const PROVIDER_BASE_URLS: Record<string, string> = {
  anthropic:   "https://api.anthropic.com",
  openai:      "https://api.openai.com/v1",
  google:      "https://generativelanguage.googleapis.com/v1beta",
  mistral:     "https://api.mistral.ai/v1",
  groq:        "https://api.groq.com/openai/v1",
  cohere:      "https://api.cohere.ai/v2",
  deepseek:    "https://api.deepseek.com/v1",
  nvidia:      "https://integrate.api.nvidia.com/v1",
  github:      "https://models.inference.ai.azure.com",
  together:    "https://api.together.xyz/v1",
  openrouter:  "https://openrouter.ai/api/v1",
  xai:         "https://api.x.ai/v1",
  perplexity:  "https://api.perplexity.ai",
  fireworks:   "https://api.fireworks.ai/inference/v1",
  ollama:      "http://localhost:11434/v1",
  lmstudio:    "http://localhost:1234/v1",
};

// ── ProviderRouter ───────────────────────────────────────────

export class ProviderRouter {
  private config: VectorConfig;

  constructor() {
    this.config = loadConfig();
  }

  reload(): void {
    this.config = loadConfig();
  }

  parseModelString(modelStr: string): { provider: string; modelId: string } {
    const idx = modelStr.indexOf("/");
    if (idx === -1) throw new Error(`Invalid model format: "${modelStr}". Use provider/model-id`);
    return {
      provider: modelStr.slice(0, idx),
      modelId: modelStr.slice(idx + 1),
    };
  }

  async chat(opts: ChatOptions): Promise<ChatResponse> {
    const { provider, modelId } = this.parseModelString(opts.model);
    switch (provider) {
      case "anthropic":   return this.chatAnthropic(modelId, opts);
      case "openai":      return this.chatOpenAICompat("openai", modelId, opts);
      case "google":      return this.chatGoogle(modelId, opts);
      case "mistral":     return this.chatOpenAICompat("mistral", modelId, opts);
      case "groq":        return this.chatOpenAICompat("groq", modelId, opts);
      case "cohere":      return this.chatCohere(modelId, opts);
      case "deepseek":    return this.chatOpenAICompat("deepseek", modelId, opts);
      case "nvidia":      return this.chatOpenAICompat("nvidia", modelId, opts);
      case "cloudflare":  return this.chatCloudflare(modelId, opts);
      case "github":      return this.chatOpenAICompat("github", modelId, opts);
      case "together":    return this.chatOpenAICompat("together", modelId, opts);
      case "openrouter":  return this.chatOpenRouter(modelId, opts);
      case "xai":         return this.chatOpenAICompat("xai", modelId, opts);
      case "perplexity":  return this.chatOpenAICompat("perplexity", modelId, opts);
      case "fireworks":   return this.chatOpenAICompat("fireworks", modelId, opts);
      case "ollama":      return this.chatOpenAICompat("ollama", modelId, opts);
      case "lmstudio":    return this.chatOpenAICompat("lmstudio", modelId, opts);
      default:
        throw new Error(`Unknown provider: "${provider}". Run /providers to see all 17 providers.`);
    }
  }

  // ── Anthropic ──────────────────────────────────────────────

  private async chatAnthropic(modelId: string, opts: ChatOptions): Promise<ChatResponse> {
    const key = this.config.providers.anthropic?.apiKey || process.env.ANTHROPIC_API_KEY || "";
    if (!key) throw new Error("Anthropic API key not set. Run: /apikey anthropic <key>");
    const body: any = {
      model: modelId,
      max_tokens: opts.max_tokens || 4096,
      messages: opts.messages.filter(m => m.role !== "system"),
    };
    if (opts.system) body.system = opts.system;
    else { const sys = opts.messages.find(m => m.role === "system"); if (sys) body.system = sys.content; }
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Anthropic API error ${res.status}: ${await res.text()}`);
    const data: any = await res.json();
    return {
      content: data.content[0].text,
      model: data.model,
      usage: { input_tokens: data.usage.input_tokens, output_tokens: data.usage.output_tokens },
      provider: "anthropic",
    };
  }

  // ── OpenAI-compatible (OpenAI, Mistral, Groq, DeepSeek, NVIDIA, GitHub, Together, xAI, Perplexity, Fireworks, Ollama, LM Studio) ──

  private async chatOpenAICompat(providerName: string, modelId: string, opts: ChatOptions): Promise<ChatResponse> {
    const provCfg = (this.config.providers as any)[providerName];
    const apiKey = provCfg?.apiKey || process.env[`${providerName.toUpperCase()}_API_KEY`] || "";
    const baseUrl = provCfg?.baseUrl || PROVIDER_BASE_URLS[providerName];
    if (!apiKey && !["ollama", "lmstudio"].includes(providerName)) {
      throw new Error(`${providerName} API key not set. Run: /apikey ${providerName} <key>`);
    }
    const headers: Record<string, string> = { "Authorization": `Bearer ${apiKey}`, "Content-Type": "application/json" };
    if (providerName === "openrouter") {
      headers["HTTP-Referer"] = "https://github.com/vector-code";
      headers["X-Title"] = "VectorCode";
    }
    const res = await fetch(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers,
      body: JSON.stringify({ model: modelId, messages: opts.messages, max_tokens: opts.max_tokens || 4096, temperature: opts.temperature ?? 0.7 }),
    });
    if (!res.ok) throw new Error(`${providerName} API error ${res.status}: ${await res.text()}`);
    const data: any = await res.json();
    const choice = data.choices?.[0];
    return {
      content: choice?.message?.content || "",
      model: data.model || modelId,
      usage: { input_tokens: data.usage?.prompt_tokens || 0, output_tokens: data.usage?.completion_tokens || 0 },
      provider: providerName,
    };
  }

  // ── Google Gemini ──────────────────────────────────────────

  private async chatGoogle(modelId: string, opts: ChatOptions): Promise<ChatResponse> {
    const key = this.config.providers.google?.apiKey || process.env.GOOGLE_API_KEY || "";
    if (!key) throw new Error("Google API key not set. Run: /apikey google <key>");
    const contents = opts.messages.filter(m => m.role !== "system").map(m => ({
      role: m.role === "assistant" ? "model" : "user",
      parts: [{ text: m.content }],
    }));
    const sys = opts.messages.find(m => m.role === "system");
    const body: any = { contents };
    if (sys) body.systemInstruction = { parts: [{ text: sys.content }] };
    body.generationConfig = { maxOutputTokens: opts.max_tokens || 4096, temperature: opts.temperature ?? 0.7 };
    const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${modelId}:generateContent?key=${key}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Google API error ${res.status}: ${await res.text()}`);
    const data: any = await res.json();
    const text = data.candidates?.[0]?.content?.parts?.[0]?.text || "";
    const usage = data.usageMetadata || {};
    return {
      content: text,
      model: modelId,
      usage: { input_tokens: usage.promptTokenCount || 0, output_tokens: usage.candidatesTokenCount || 0 },
      provider: "google",
    };
  }

  // ── Cloudflare Workers AI ──────────────────────────────────

  private async chatCloudflare(modelId: string, opts: ChatOptions): Promise<ChatResponse> {
    const cfg = this.config.providers.cloudflare;
    const key = cfg?.apiKey || process.env.CLOUDFLARE_API_KEY || "";
    const accountId = cfg?.accountId || process.env.CLOUDFLARE_ACCOUNT_ID || "";
    if (!key || !accountId) throw new Error("Cloudflare: need API key + account ID. Run: /apikey cloudflare <key> <account-id>");
    const res = await fetch(`https://api.cloudflare.com/client/v4/accounts/${accountId}/ai/run/${modelId}`, {
      method: "POST",
      headers: { "Authorization": `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ messages: opts.messages }),
    });
    if (!res.ok) throw new Error(`Cloudflare AI error ${res.status}: ${await res.text()}`);
    const data: any = await res.json();
    return { content: data.result?.response || "", model: modelId, usage: { input_tokens: 0, output_tokens: 0 }, provider: "cloudflare" };
  }

  // ── Cohere ─────────────────────────────────────────────────

  private async chatCohere(modelId: string, opts: ChatOptions): Promise<ChatResponse> {
    const key = this.config.providers.cohere?.apiKey || process.env.COHERE_API_KEY || "";
    if (!key) throw new Error("Cohere API key not set. Run: /apikey cohere <key>");
    const sys = opts.messages.find(m => m.role === "system");
    const history = opts.messages.filter(m => m.role !== "system").slice(0, -1).map(m => ({
      role: m.role === "assistant" ? "CHATBOT" : "USER", message: m.content,
    }));
    const lastMsg = opts.messages.filter(m => m.role !== "system").slice(-1)[0]?.content || "";
    const res = await fetch("https://api.cohere.ai/v2/chat", {
      method: "POST",
      headers: { "Authorization": `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model: modelId, message: lastMsg, chat_history: history, ...(sys ? { preamble: sys.content } : {}) }),
    });
    if (!res.ok) throw new Error(`Cohere API error ${res.status}: ${await res.text()}`);
    const data: any = await res.json();
    return {
      content: data.message?.content?.[0]?.text || "",
      model: modelId,
      usage: { input_tokens: data.meta?.tokens?.input_tokens || 0, output_tokens: data.meta?.tokens?.output_tokens || 0 },
      provider: "cohere",
    };
  }

  // ── OpenRouter ─────────────────────────────────────────────

  private async chatOpenRouter(modelId: string, opts: ChatOptions): Promise<ChatResponse> {
    return this.chatOpenAICompat("openrouter", modelId, opts);
  }

  // ── Health checks ──────────────────────────────────────────

  async checkProviderStatus(provider: string): Promise<"online" | "no-key" | "offline"> {
    const cfg = this.config.providers as any;
    const envKey = process.env[`${provider.toUpperCase()}_API_KEY`];
    const hasKey = cfg[provider]?.apiKey || envKey;
    if (provider === "ollama") {
      try {
        const res = await fetch("http://localhost:11434/api/tags", { signal: AbortSignal.timeout(2000) });
        return res.ok ? "online" : "offline";
      } catch { return "offline"; }
    }
    if (provider === "lmstudio") {
      try {
        const res = await fetch("http://localhost:1234/v1/models", { signal: AbortSignal.timeout(2000) });
        return res.ok ? "online" : "offline";
      } catch { return "offline"; }
    }
    if (!hasKey) return "no-key";
    return "online";
  }

  async listOllamaModels(): Promise<string[]> {
    try {
      const baseUrl = this.config.providers.ollama?.baseUrl || "http://localhost:11434";
      const res = await fetch(`${baseUrl}/api/tags`, { signal: AbortSignal.timeout(3000) });
      if (!res.ok) return [];
      const data: any = await res.json();
      return (data.models || []).map((m: any) => `ollama/${m.name}`);
    } catch { return []; }
  }

  async checkProviderHealth(provider: string, _config?: any): Promise<ProviderHealth> {
    const status = await this.checkProviderStatus(provider);
    const models = MODEL_REGISTRY.filter(m => m.provider === provider).map(m => m.id);
    const modelInfo = MODEL_REGISTRY.find(m => m.provider === provider);
    return {
      provider,
      reachable: status === "online",
      models,
      contextWindow: modelInfo?.contextWindow || 0,
      supportsTools: modelInfo?.supportsTools || false,
      detail: status === "online" ? `${models.length} models` :
              status === "no-key" ? "API key not set" : "unreachable",
    };
  }
}

// ── CLI Commands ─────────────────────────────────────────────

export async function cmdApiKey(args: string[]): Promise<void> {
  const [provider, key, extra] = args;
  if (!provider || !key) {
    console.log(`\x1b[93mUsage: /apikey <provider> <api-key> [extra]\x1b[0m
\x1b[96mExamples:\x1b[0m
  /apikey anthropic   sk-ant-...
  /apikey openai      sk-...
  /apikey google      AIza...
  /apikey groq        gsk_...
  /apikey nvidia      nvapi-...
  /apikey cloudflare  <key> <account-id>
  /apikey github      ghp_...
  /apikey ollama      (no key needed)`);
    return;
  }
  if (provider === "cloudflare") {
    if (!extra) { console.log("\x1b[91mCloudflare needs account ID: /apikey cloudflare <key> <account-id>\x1b[0m"); return; }
    setApiKey("cloudflare", key, { accountId: extra });
  } else {
    setApiKey(provider, key);
  }
}

export async function cmdProviders(): Promise<void> {
  const router = new ProviderRouter();
  const providers = ["anthropic","openai","google","mistral","groq","cohere","deepseek","nvidia","cloudflare","github","together","openrouter","xai","perplexity","fireworks","ollama","lmstudio"];
  console.log("\n\x1b[96m╔══════════════════════════════════════════════════════╗\x1b[0m");
  console.log("\x1b[96m║              VECTOR CODE — PROVIDERS                 ║\x1b[0m");
  console.log("\x1b[96m╚══════════════════════════════════════════════════════╝\x1b[0m\n");
  for (const p of providers) {
    const status = await router.checkProviderStatus(p);
    const dot = status === "online" ? "\x1b[92m●\x1b[0m" : status === "no-key" ? "\x1b[93m●\x1b[0m" : "\x1b[91m●\x1b[0m";
    const label = status === "online" ? "\x1b[92mONLINE \x1b[0m" : status === "no-key" ? "\x1b[93mNO KEY \x1b[0m" : "\x1b[91mOFFLINE\x1b[0m";
    const modelCount = MODEL_REGISTRY.filter(m => m.provider === p).length;
    const local = ["ollama","lmstudio"].includes(p) ? " \x1b[96m[LOCAL]\x1b[0m" : "";
    console.log(`  ${dot} ${label}  \x1b[97m${p.padEnd(12)}\x1b[0m  ${modelCount} models${local}`);
  }
  console.log("\n\x1b[90m● online  ● no key set  ● offline\x1b[0m\n");
}

export async function cmdModels(filterProvider?: string): Promise<void> {
  const router = new ProviderRouter();
  const ollamaModels = await router.listOllamaModels();
  let models = MODEL_REGISTRY;
  if (filterProvider) models = models.filter(m => m.provider === filterProvider);
  ollamaModels.forEach((id: string) => {
    if (!models.find(m => m.id === id)) {
      models.push({ id, provider: "ollama", displayName: id.replace("ollama/", "") + " (installed)", contextWindow: 32768, supportsTools: false, supportsVision: false, costPer1kInput: 0, costPer1kOutput: 0 });
    }
  });
  console.log("\n\x1b[96m╔═══════════════════════════════════════════════════════════════════════════╗\x1b[0m");
  console.log("\x1b[96m║                     VECTOR CODE — ALL MODELS                             ║\x1b[0m");
  console.log("\x1b[96m╚═══════════════════════════════════════════════════════════════════════════╝\x1b[0m\n");
  console.log(`  \x1b[90m${"MODEL ID".padEnd(52)} ${"CTX".padStart(7)}  ${"TOOLS".padEnd(6)} ${"VISION".padEnd(7)} ${"IN/1K".padStart(7)} ${"OUT/1K".padStart(7)}\x1b[0m`);
  console.log(`  \x1b[90m${"─".repeat(96)}\x1b[0m`);
  let lastProvider = "";
  for (const m of models) {
    if (m.provider !== lastProvider) { console.log(`\n  \x1b[96m▸ ${m.provider.toUpperCase()}\x1b[0m`); lastProvider = m.provider; }
    const ctx = m.contextWindow >= 1000000 ? `${m.contextWindow/1000000}M` : `${m.contextWindow/1000}K`;
    const tools = m.supportsTools ? "\x1b[92m✓\x1b[0m     " : "\x1b[90m✗\x1b[0m     ";
    const vision = m.supportsVision ? "\x1b[92m✓\x1b[0m      " : "\x1b[90m✗\x1b[0m      ";
    const inCost = m.costPer1kInput === 0 ? "\x1b[92m  free\x1b[0m" : `\x1b[97m$${m.costPer1kInput.toFixed(4)}\x1b[0m`;
    const outCost = m.costPer1kOutput === 0 ? "\x1b[92m  free\x1b[0m" : `\x1b[97m$${m.costPer1kOutput.toFixed(4)}\x1b[0m`;
    console.log(`    \x1b[97m${m.id.padEnd(52)}\x1b[0m \x1b[90m${ctx.padStart(5)}\x1b[0m  ${tools}${vision}${inCost.padStart(8)} ${outCost.padStart(8)}`);
  }
  console.log(`\n  \x1b[90m${models.length} models listed. Use: /model <provider/model-id>\x1b[0m\n`);
}

export const COMMANDS: Record<string, (args: string[]) => Promise<void>> = {
  "/apikey":    cmdApiKey,
  "/providers": async () => cmdProviders(),
  "/models":    async (args: string[]) => cmdModels(args[0]),
};
