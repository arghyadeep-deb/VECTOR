import { LoopIteration } from "../agent/loop.js";

export class ContextManager {
  hydrate(task: string): string {
    return `Task: ${task}\n\n`;
  }

  compact(context: string, iterations: LoopIteration[]): string {
    const last = iterations.slice(-3);
    const summary = last.map(i =>
      `[${i.n}] ${i.toolCall?.name ?? "respond"} → ${i.toolResult ? `${i.toolResult.output.length} chars` : "done"}`
    ).join("\n");
    return `[Context compacted — ${iterations.length} iterations so far]\n${summary}\n\n${context.slice(-20000)}`;
  }
}
