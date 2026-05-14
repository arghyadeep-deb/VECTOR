export class MCPClient {
  private servers: Map<string, any> = new Map();

  async connect(name: string, command: string, args: string[]): Promise<void> {
    this.servers.set(name, { command, args, connected: true });
  }

  async call(_server: string, _tool: string, _args: Record<string, any>): Promise<any> {
    return { result: "not implemented" };
  }

  listServers(): string[] {
    return Array.from(this.servers.keys());
  }
}
