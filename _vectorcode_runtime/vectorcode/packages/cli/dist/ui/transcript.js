import wrapAnsi from 'wrap-ansi';
import { Chalk } from 'chalk';
import stripAnsi from 'strip-ansi';
export function transcriptLines(messages, width) {
    const color = new Chalk({ level: 3 });
    const lines = [];
    for (const message of messages) {
        const label = message.role === 'user' ? 'YOU' : message.role === 'assistant' ? 'VECTOR' : message.role === 'tool' ? message.toolName || 'TOOL' : 'SYSTEM';
        const tint = message.role === 'user' ? '#c7adf3' : message.role === 'assistant' ? '#9ee6bf' : '#858b94';
        lines.push('', color.hex(tint).bold(label));
        let code = false;
        const raw = message.role === 'tool' ? message.content.slice(0, 500) : message.content;
        const content = stripAnsi(raw).replace(/[\x00-\x08\x0b-\x1f\x7f]/g, '');
        for (const line of content.split('\n')) {
            let rendered;
            if (line.trimStart().startsWith('```')) {
                code = !code;
                rendered = color.hex('#858b94')(code ? `┌ ${line.replace(/```/, '') || 'code'}` : '└');
            }
            else if (code) {
                rendered = color.hex(line.startsWith('+') ? '#9ee6bf' : line.startsWith('-') ? '#f38b8b' : '#90b9dc')('│ ' + line);
            }
            else if (/^#{1,6} /.test(line)) {
                rendered = color.bold(line.replace(/^#{1,6} /, ''));
            }
            else {
                rendered = line.replace(/\*\*(.+?)\*\*/g, (_, text) => color.bold(text))
                    .replace(/`([^`]+)`/g, (_, text) => color.hex('#e5bd7a')(text));
            }
            lines.push(...wrapAnsi(rendered, Math.max(10, width), { hard: true, trim: false }).split('\n'));
        }
    }
    return lines;
}
export function viewport(lines, height, offset) {
    const end = Math.max(height, lines.length - Math.max(0, offset));
    return lines.slice(Math.max(0, end - height), end);
}
//# sourceMappingURL=transcript.js.map