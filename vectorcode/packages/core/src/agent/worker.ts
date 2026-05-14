import { ToolCall, ToolResult } from "../tools/index.js";

export interface WorkerTask {
  id: string;
  description: string;
  result?: string;
}

export class WorkerAgent {
  async execute(_task: WorkerTask): Promise<string> {
    return `[worker] task ${_task.id} completed`;
  }
}
