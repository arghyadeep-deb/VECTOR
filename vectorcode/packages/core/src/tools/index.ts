export interface ToolCall {
  name: string;
  args: Record<string, any>;
}

export interface ToolResult {
  tool: string;
  output: string;
  error?: string;
  durationMs: number;
}

export interface ToolDef {
  name: string;
  description: string;
  isReadOnly: boolean;
  riskLevel: "safe" | "low" | "medium" | "high" | "critical";
  run: (args: Record<string, any>) => Promise<string>;
}

export class ToolExecutor {
  private tools: Map<string, ToolDef> = new Map();

  constructor(private config: { toolTimeoutMs: number }) {
    this.registerDefaultTools();
  }

  private registerDefaultTools(): void {
    this.register({
      name: "read_file",
      description: "Read contents of a file",
      isReadOnly: true,
      riskLevel: "safe",
      run: async (args) => {
        const fs = await import("fs/promises");
        return fs.readFile(args.path, "utf-8");
      },
    });

    this.register({
      name: "write_file",
      description: "Write content to a file",
      isReadOnly: false,
      riskLevel: "medium",
      run: async (args) => {
        const fs = await import("fs/promises");
        await fs.writeFile(args.path, args.content, "utf-8");
        return `Written ${args.path} (${args.content.length} chars)`;
      },
    });

    this.register({
      name: "edit_file",
      description: "Precise string-replace edit",
      isReadOnly: false,
      riskLevel: "medium",
      run: async (args) => {
        const fs = await import("fs/promises");
        const content = await fs.readFile(args.path, "utf-8");
        const updated = content.replace(args.oldString, args.newString);
        if (updated === content) return "No match found for oldString";
        await fs.writeFile(args.path, updated, "utf-8");
        return `Edited ${args.path}`;
      },
    });

    this.register({
      name: "bash",
      description: "Execute a shell command",
      isReadOnly: false,
      riskLevel: "high",
      run: async (args) => {
        const { execSync } = await import("child_process");
        const out = execSync(args.command, {
          encoding: "utf-8",
          timeout: 15_000,
          maxBuffer: 10 * 1024 * 1024,
        });
        return out;
      },
    });

    this.register({
      name: "glob",
      description: "Find files matching a pattern",
      isReadOnly: true,
      riskLevel: "safe",
      run: async (args) => {
        const { globSync } = await import("fs");
        const results = globSync(args.pattern) as string[];
        return results.join("\n");
      },
    });

    this.register({
      name: "grep",
      description: "Search file contents with regex",
      isReadOnly: true,
      riskLevel: "safe",
      run: async (args) => {
        const { execSync } = await import("child_process");
        return execSync(
          `grep -rn "${args.pattern}" ${args.path || "."} --include="*.${args.include || "*"}"`,
          { encoding: "utf-8", timeout: 10_000 }
        );
      },
    });

    this.register({
      name: "git_status",
      description: "Get working tree status",
      isReadOnly: true,
      riskLevel: "safe",
      run: async () => {
        const { execSync } = await import("child_process");
        return execSync("git status", { encoding: "utf-8" });
      },
    });

    this.register({
      name: "git_diff",
      description: "Show diff of changes",
      isReadOnly: true,
      riskLevel: "safe",
      run: async () => {
        const { execSync } = await import("child_process");
        return execSync("git diff", { encoding: "utf-8" });
      },
    });

    this.register({
      name: "web_search",
      description: "Search the web",
      isReadOnly: true,
      riskLevel: "low",
      run: async (args) => {
        const url = `https://api.duckduckgo.com/?q=${encodeURIComponent(args.query)}&format=json`;
        const resp = await fetch(url);
        return JSON.stringify(await resp.json(), null, 2);
      },
    });
  }

  register(def: ToolDef): void {
    this.tools.set(def.name, def);
  }

  get(name: string): ToolDef | undefined {
    return this.tools.get(name);
  }

  list(): ToolDef[] {
    return Array.from(this.tools.values());
  }

  async execute(tc: ToolCall): Promise<ToolResult> {
    const def = this.tools.get(tc.name);
    if (!def) {
      return {
        tool: tc.name,
        output: "",
        error: `Unknown tool: ${tc.name}`,
        durationMs: 0,
      };
    }
    const start = Date.now();
    try {
      const output = await def.run(tc.args);
      return { tool: tc.name, output, durationMs: Date.now() - start };
    } catch (e: any) {
      return {
        tool: tc.name,
        output: "",
        error: e.message ?? String(e),
        durationMs: Date.now() - start,
      };
    }
  }
}
