export class SessionMemory {
  private store: Record<string, string> = {};

  get(key: string): string | undefined {
    return this.store[key];
  }

  set(key: string, value: string): void {
    this.store[key] = value;
  }

  getAll(): Record<string, string> {
    return { ...this.store };
  }

  keys(): string[] {
    return Object.keys(this.store);
  }
}
