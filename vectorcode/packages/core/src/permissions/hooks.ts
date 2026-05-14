export interface HookDef {
  event: string;
  command: string;
}

export class HookRunner {
  private hooks: HookDef[] = [];

  register(h: HookDef): void {
    this.hooks.push(h);
  }

  async run(event: string, vars: Record<string, string>): Promise<void> {
    for (const h of this.hooks) {
      if (h.event === event) {
        const cmd = h.command.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
        try {
          const { execSync } = await import("child_process");
          execSync(cmd, { encoding: "utf-8", timeout: 10_000 });
        } catch {
          // hook failure is non-fatal
        }
      }
    }
  }
}
