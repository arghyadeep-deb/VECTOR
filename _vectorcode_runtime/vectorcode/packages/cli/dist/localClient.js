import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
export class LocalClient {
    listener;
    child;
    closing = false;
    constructor(listener, python = process.env.VECTOR_PYTHON || 'python') {
        this.listener = listener;
        const root = process.env.VECTOR_CODING_ROOT || fileURLToPath(new URL('../../../../', import.meta.url));
        this.child = spawn(python, ['-m', 'vectorcode.src.terminal_bridge'], {
            cwd: root, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
            env: { ...process.env, PYTHONIOENCODING: 'utf-8', VECTOR_INTERACTIVE: '1' },
        });
        createInterface({ input: this.child.stdout }).on('line', line => {
            try {
                this.listener(JSON.parse(line));
            }
            catch { /* Ignore non-protocol output. */ }
        });
        this.child.stderr.resume();
        this.child.on('error', () => this.listener({ type: 'error', message: 'Could not start Python. Check VECTOR_PYTHON.' }));
        this.child.on('close', () => this.listener({ type: 'offline', message: 'Local coding process stopped. Restart VectorCode.' }));
        this.child.stdin.on('error', () => this.listener({ type: 'offline', message: 'Local coding process disconnected.' }));
    }
    send(request) {
        if (!this.closing && this.child.stdin.writable)
            this.child.stdin.write(JSON.stringify(request) + '\n');
    }
    run(request) { this.send({ command: 'run', ...request }); }
    approve(id, allow) { this.send({ command: 'approve', id, allow }); }
    cancel() { this.send({ command: 'cancel' }); }
    close() {
        if (this.closing)
            return;
        this.cancel();
        this.closing = true;
        this.child.stdin.end();
    }
}
//# sourceMappingURL=localClient.js.map