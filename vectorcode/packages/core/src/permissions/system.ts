import { ToolCall } from "../tools/index.js";

export type PermissionVerdict = "allow" | "ask" | "deny";

export class PermissionSystem {
  private mode: "cautious" | "standard" | "autonomous" | "read-only" = "cautious";
  private approvedOnce: Set<string> = new Set();

  setMode(m: typeof this.mode): void {
    this.mode = m;
  }

  getMode(): string {
    return this.mode;
  }

  check(tc: ToolCall): PermissionVerdict {
    if (this.mode === "read-only") {
      return tc.name.startsWith("read_") || tc.name.startsWith("git_") ? "allow" : "deny";
    }
    if (this.mode === "autonomous") return "allow";

    const riskMap: Record<string, string> = {
      read_file: "safe",
      write_file: "medium",
      edit_file: "medium",
      bash: "high",
      glob: "safe",
      grep: "safe",
      git_status: "safe",
      git_diff: "safe",
      git_commit: "medium",
      git_push: "high",
      web_search: "low",
      web_fetch: "low",
    };

    const risk = riskMap[tc.name] || "medium";

    if (risk === "safe" || risk === "low") return "allow";
    if (risk === "medium" && this.approvedOnce.has(tc.name)) return "allow";
    if (risk === "medium" && this.mode === "cautious") return "ask";
    if (risk === "medium" && this.mode === "standard") {
      this.approvedOnce.add(tc.name);
      return "allow";
    }
    if (risk === "high" || risk === "critical") return "ask";

    return "allow";
  }

  approve(tcName: string): void {
    this.approvedOnce.add(tcName);
  }
}
