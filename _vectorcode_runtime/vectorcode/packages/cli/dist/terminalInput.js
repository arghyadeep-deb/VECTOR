/** Normalize Backspace before Ink 5 discards raw key sequences, retaining the real TTY lifecycle. */
export function terminalInput(source) {
    const originalRead = source.read;
    const read = (size) => {
        const chunk = originalRead.call(source, size);
        if (typeof chunk === 'string')
            return chunk.replace(/\x7f/g, '\x08');
        if (!Buffer.isBuffer(chunk))
            return chunk;
        const normalized = Buffer.from(chunk);
        for (let index = 0; index < normalized.length; index++) {
            if (normalized[index] === 0x7f)
                normalized[index] = 0x08;
        }
        return normalized;
    };
    source.read = read;
    return {
        input: source,
        close() { if (source.read === read)
            source.read = originalRead; },
    };
}
//# sourceMappingURL=terminalInput.js.map