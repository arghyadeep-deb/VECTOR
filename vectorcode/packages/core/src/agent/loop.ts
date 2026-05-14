import { ToolExecutor, ToolResult, ToolCall } from "../tools/index.js";
import { ContextManager } from "../context/manager.js";
import { PermissionSystem } from "../permissions/system.js";
import { ProviderRouter } from "../providers/index.js";
import { SessionMemory } from "../context/memory.js";

export interface LoopConfig {
  maxIterations: number;
  toolTimeoutMs: number;
  verbose: boolean;
}

const DEFAULT_CONFIG: LoopConfig = {
  maxIterations: 50,
  toolTimeoutMs: 30_000,
  verbose: false,
};

export interface LoopIteration {
  n: number;
  thought: string;
  toolCall: ToolCall | null;
  toolResult: ToolResult | null;
  done: boolean;
  reason: string;
}

export class AgenticLoop {
  private config: LoopConfig;
  private tools: ToolExecutor;
  private context: ContextManager;
  private permissions: PermissionSystem;
  private router: ProviderRouter;
  private memory: SessionMemory;
  private iterations: LoopIteration[] = [];

  constructor(opts?: Partial<LoopConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...opts };
    this.tools = new ToolExecutor(this.config);
    this.context = new ContextManager();
    this.permissions = new PermissionSystem();
    this.router = new ProviderRouter();
    this.memory = new SessionMemory();
  }

  setVerbose(v: boolean): void {
    this.config.verbose = v;
  }

  getIterations(): readonly LoopIteration[] {
    return this.iterations;
  }

  async run(task: string): Promise<string> {
    this.iterations = [];
    let context = this.context.hydrate(task);

    for (let n = 1; n <= this.config.maxIterations; n++) {
      // ── THINK ──
      const thought = await this.think(context, task, n);
      if (this.config.verbose) {
        process.stderr.write(
          `\x1b[96m[THINK]\x1b[0m iteration ${n} → \x1b[90m${thought.slice(0, 120)}...\x1b[0m\n`
        );
      }

      // ── ACT ──
      const toolCall = this.parseToolCall(thought);
      if (!toolCall) {
        const done = true;
        const reason = "no tool call — model wants to respond";
        this.iterations.push({
          n, thought, toolCall: null, toolResult: null, done, reason,
        });
        if (this.config.verbose) {
          process.stderr.write(
            `\x1b[96m[DONE?]\x1b[0m stopping because: ${reason}\n`
          );
        }
        return thought;
      }

      // Permission gate
      const gate = this.permissions.check(toolCall);
      if (gate === "deny") {
        const result: ToolResult = {
          tool: toolCall.name,
          output: "",
          error: `Permission denied: ${toolCall.name} is RED-gated`,
          durationMs: 0,
        };
        this.iterations.push({
          n, thought, toolCall, toolResult: result, done: false, reason: "permission denied",
        });
        context += `\n[TOOL RESULT] ${toolCall.name} failed: permission denied\n`;
        continue;
      }

      if (this.config.verbose) {
        process.stderr.write(
          `\x1b[96m[ACT]\x1b[0m calling tool: \x1b[92m${toolCall.name}\x1b[0m`
          + ` with args: ${JSON.stringify(toolCall.args).slice(0, 100)}...\n`
        );
      }

      // ── OBSERVE (with timeout) ──
      const result = await this.executeWithTimeout(toolCall);

      if (this.config.verbose) {
        const preview = result.output
          ? `${result.output.length} chars`
          : `error: ${(result.error ?? "").slice(0, 60)}`;
        process.stderr.write(
          `\x1b[96m[OBSERVE]\x1b[0m result length: ${preview}\n`
        );
      }

      this.iterations.push({
        n, thought, toolCall, toolResult: result, done: false, reason: "continuing",
      });

      // ── DONE? ──
      if (result.error) {
        context += `\n[TOOL ERROR] ${result.tool}: ${result.error}\n`;
      } else {
        context += `\n[TOOL RESULT] ${result.tool} (${result.output.length} chars):\n${result.output.slice(0, 2000)}\n`;
      }

      // Check if context is too large
      if (context.length > 100_000) {
        context = this.context.compact(context, this.iterations);
      }

      if (n >= this.config.maxIterations) {
        if (this.config.verbose) {
          process.stderr.write(
            `\x1b[96m[DONE?]\x1b[0m stopping because: max iterations (${this.config.maxIterations}) reached\n`
          );
        }
        return `[VECTOR] Reached max iterations (${this.config.maxIterations}). Here's what was done:\n`
          + this.summarize();
      }
    }

    return `[VECTOR] Task completed.\n${this.summarize()}`;
  }

  private async think(context: string, task: string, n: number): Promise<string> {
    const activeModel = process.env.VECTOR_MODEL || "ollama/vector-focus";
    const prompt = `You are VECTOR, a terminal-native coding agent.\n\n`
      + `Task: ${task}\n\n`
      + `Context so far:\n${context.slice(-8000)}\n\n`
      + `Iteration ${n}/${this.config.maxIterations}.\n`
      + `Decide the next action. Respond with a tool call in format:\n`
      + `{{TOOL name="tool_name" args={key:"value"}}}\n`
      + `Or respond naturally if the task is complete.`;
    try {
      const resp = await this.router.chat({
        model: activeModel,
        messages: [{ role: "user", content: prompt }],
        max_tokens: 4096,
      });
      return resp.content;
    } catch (e: any) {
      return `[VECTOR] LLM error: ${e.message}`;
    }
  }

  private parseToolCall(thought: string): ToolCall | null {
    const match = thought.match(/\{\{TOOL\s+name="([^"]+)"\s+args=\{(.+?)\}\}\}/s);
    if (!match) return null;
    try {
      const args = JSON.parse(`{${match[2]}}`);
      return { name: match[1], args };
    } catch {
      return { name: match[1], args: { raw: match[2] } };
    }
  }

  private async executeWithTimeout(tc: ToolCall): Promise<ToolResult> {
    return Promise.race([
      this.tools.execute(tc),
      new Promise<ToolResult>((_, reject) =>
        setTimeout(() => reject(new Error(
          `Tool ${tc.name} timed out after ${this.config.toolTimeoutMs}ms`
        )), this.config.toolTimeoutMs)
      ).catch((err: Error) => ({
        tool: tc.name,
        output: "",
        error: err.message,
        durationMs: this.config.toolTimeoutMs,
      })),
    ]);
  }

  private summarize(): string {
    const calls = this.iterations.filter(i => i.toolCall);
    return `${calls.length} tool calls executed.`
      + ` Run with --verbose for full iteration log.`;
  }
}
