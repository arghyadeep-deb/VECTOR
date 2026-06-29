import { cpSync, existsSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const cwd = resolve(process.cwd());
const args = ["run", ...process.argv.slice(2)];

function runVitest(workdir) {
  const bin = process.platform === "win32"
    ? join(workdir, "node_modules", ".bin", "vitest.cmd")
    : join(workdir, "node_modules", ".bin", "vitest");
  const result = spawnSync(bin, args, {
    cwd: workdir,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.error) {
    console.error(result.error.message);
    return 1;
  }
  return result.status ?? 1;
}

if (!/\s/.test(cwd)) {
  process.exit(runVitest(cwd));
}

const safeRoot = join(tmpdir(), "vector-api-vitest-nospace");
mkdirSync(safeRoot, { recursive: true });
const tempRoot = mkdtempSync(join(safeRoot, "vector-api-vitest-"));
const target = join(tempRoot, basename(cwd).replace(/\s+/g, "_"));

try {
  cpSync(cwd, target, {
    recursive: true,
    force: true,
    filter: (src) => {
      const normal = src.replaceAll("\\", "/");
      return !normal.includes("/.wrangler/")
        && !normal.includes("/.wrangler-local-state/")
        && !normal.includes("/.claude/");
    },
  });
} catch (_error) {
  const fallbackRoot = join(tmpdir(), "vector-api-vitest-nospace");
  const fallbackTarget = join(fallbackRoot, basename(cwd).replace(/\s+/g, "_"));
  rmSync(fallbackRoot, { recursive: true, force: true });
  cpSync(cwd, fallbackTarget, {
    recursive: true,
    force: true,
    filter: (src) => {
      const normal = src.replaceAll("\\", "/");
      return !normal.includes("/.wrangler/")
        && !normal.includes("/.wrangler-local-state/")
        && !normal.includes("/.claude/");
    },
  });
  if (!existsSync(join(fallbackTarget, "node_modules", ".bin"))) {
    console.error("Copied API test tree is missing node_modules/.bin; run npm install in api first.");
    process.exit(1);
  }
  process.exit(runVitest(fallbackTarget));
}

if (!existsSync(join(target, "node_modules", ".bin"))) {
  console.error("Copied API test tree is missing node_modules/.bin; run npm install in api first.");
  process.exit(1);
}

process.exit(runVitest(target));
