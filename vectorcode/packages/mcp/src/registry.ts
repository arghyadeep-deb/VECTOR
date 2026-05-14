export interface MCPServerConfig {
  name: string;
  type: "stdio" | "http";
  command: string;
  args: string[];
  env?: Record<string, string>;
}

export class MCPRegistry {
  private servers: MCPServerConfig[] = [];

  register(config: MCPServerConfig): void {
    this.servers.push(config);
  }

  remove(name: string): void {
    this.servers = this.servers.filter(s => s.name !== name);
  }

  list(): MCPServerConfig[] {
    return [...this.servers];
  }
}
