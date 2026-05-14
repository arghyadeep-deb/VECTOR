export class ContextCompactor {
  compact(context: string, _iterations: number): string {
    const maxLen = 80_000;
    if (context.length <= maxLen) return context;
    const head = context.slice(0, 20_000);
    const tail = context.slice(-50_000);
    const summary = `\n[... ${context.length - maxLen} chars compacted ...]\n`;
    return head + summary + tail;
  }
}
