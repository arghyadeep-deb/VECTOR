export const PROMPT = "\x1b[96mvector\u276F\x1b[0m ";

export function printBanner(
  modelName: string,
  ollamaModels: string[],
  hasVectorMd: boolean,
): void {
  const C = {
    c: "\x1b[36m",   // cyan dim
    C: "\x1b[96m",   // cyan bright
    w: "\x1b[97m\x1b[1m", // white bold
    b: "\x1b[34m",   // blue dim
    g: "\x1b[92m",   // green
    a: "\x1b[93m",   // amber
    r: "\x1b[0m",    // reset
    d: "\x1b[2m",    // dim
  };

  const W = 72, I = 4, IW = W - 2 * I - 2, CW = W - 2;
  const D = "\u2500", TT = "\u252C", TB = "\u2534", DOT = "\xB7";
  const ring = (inner: string) => `${C.c}\u2502${C.r} ${C.C}\u2502${C.r}${inner}${C.C}\u2502${C.r} ${C.c}\u2502${C.r}`;

  const dotLine = () => {
    const a = new Array(CW + 1).join(" ");
    return a.slice(0, Math.floor(CW * 0.2)) + DOT + a.slice(Math.floor(CW * 0.2) + 1)
      .slice(0, Math.floor(CW * 0.5)) + DOT + a.slice(Math.floor(CW * 0.5) + 1)
      .slice(0, Math.floor(CW * 0.8)) + DOT + a.slice(Math.floor(CW * 0.8) + 1);
  };

  const tickL = (t: string) => {
    const seg = t + "    ", rep = Math.floor(IW / seg.length);
    return " ".repeat(Math.floor((IW - rep * seg.length) / 2)) + seg.repeat(rep) + t
      + " ".repeat(Math.ceil((IW - rep * seg.length) / 2));
  };

  const pad = (s: string, w: number) => {
    const v = s.replace(/\x1b\[[0-9;]*m/g, "");
    const p = w - v.length;
    return p <= 0 ? s : " ".repeat(Math.floor(p / 2)) + s + " ".repeat(Math.ceil(p / 2));
  };

  const dots = dotLine();
  const sep = `${C.b}${D.repeat(20)}${C.r}`;
  const blines = [
    `${C.c}\u256D${D.repeat(CW)}\u256E${C.r}`,
    `${C.c}\u2502${C.r}${C.b}${dots}${C.r}${C.c}\u2502${C.r}`,
    `${C.c}\u2502${C.r} ${C.C}\u25DC${D.repeat(IW)}\u25DD${C.r} ${C.c}\u2502${C.r}`,
    `${C.C}\u2524${C.r} ${C.c}\u2502${C.r}${C.C}${tickL(TT)}${C.r}${C.c}\u2502${C.r} ${C.C}\u251C${C.r}`,
    ring(pad(`${C.w}V.E.C.T.O.R.${C.r}`, IW)),
    ring(pad(sep, IW)),
    ring(pad(`${C.b}${C.d}VIRTUAL ENTITY FOR COGNITIVE TASKS & OP. REASONING${C.r}`, IW)),
    `${C.C}\u2524${C.r} ${C.c}\u2502${C.r}${C.C}${tickL(TB)}${C.r}${C.c}\u2502${C.r} ${C.C}\u251C${C.r}`,
    `${C.c}\u2502${C.r} ${C.C}\u25DE${D.repeat(IW)}\u25DF${C.r} ${C.c}\u2502${C.r}`,
    `${C.c}\u2502${C.r}${C.b}${dots}${C.r}${C.c}\u2502${C.r}`,
    `${C.c}\u2570${D.repeat(CW)}\u256F${C.r}`,
  ];

  // Status block
  const now = new Date();
  const uptime = `${String(now.getUTCHours()).padStart(2,"0")}:${String(now.getUTCMinutes()).padStart(2,"0")}:${String(now.getUTCSeconds()).padStart(2,"0")}`;
  const sLines = [
    `${C.b}${D.repeat(W)}${C.r}`,
    `${C.c} STATUS    ${C.r}${C.b}\u2502${C.r}  ${C.g}ONLINE${C.r}`,
    `${C.c} UPTIME    ${C.r}${C.b}\u2502${C.r}  ${C.w}${uptime}${C.r}`,
    `${C.c} MODE      ${C.r}${C.b}\u2502${C.r}  ${C.w}repl${C.r}`,
    `${C.c} MODEL     ${C.r}${C.b}\u2502${C.r}  ${C.w}${modelName || "(none)"}${C.r}`,
    `${C.c} SKILLS    ${C.r}${C.b}\u2502${C.r}  ${C.w}64 loaded${C.r}`,
    `${C.c} MEMORY    ${C.r}${C.b}\u2502${C.r}  ${C.w}.vector/memory.md${C.r}`,
    `${C.b}${D.repeat(W)}${C.r}`,
  ];

  // Print everything
  console.log();
  for (const l of blines) console.log("  " + l);
  console.log();
  for (const l of sLines) console.log("  " + l);
  console.log();

  // Ollama status
  if (!ollamaModels || ollamaModels.length === 0) {
    console.log(`  ${C.a}\u25CF Ollama offline \u2014 local models unavailable${C.r}`);
  } else {
    const names = ollamaModels.slice(0, 6).map(m => m.replace(/^ollama\//, ""));
    const suffix = ollamaModels.length > 6 ? ` ${C.d}${C.b}\u2026${C.r}` : "";
    console.log(`  ${C.g}\u25CF Ollama online \u2014 ${ollamaModels.length} models available${C.r}`);
    console.log(`  ${C.d}${C.c}Models: ${names.join(", ")}${suffix}${C.r}`);
  }

  // VECTOR.md status
  console.log(hasVectorMd
    ? `  ${C.g}\uD83D\uDCCB VECTOR.md loaded${C.r}`
    : `  ${C.a}\uD83D\uDCA1 No VECTOR.md found \u2014 run /init to create one${C.r}`);
  console.log();
}
