import { ToolCall } from "../tools/index.js";

export interface Plan {
  task: string;
  steps: ToolCall[];
}

export class Planner {
  plan(task: string): Plan {
    return { task, steps: [] };
  }
}
