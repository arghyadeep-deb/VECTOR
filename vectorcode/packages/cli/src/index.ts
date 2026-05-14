#!/usr/bin/env node
import { Command } from "commander";

const program = new Command();

program
  .name("vector")
  .description("Vector Code — Terminal-Native, Model-Agnostic Agentic Coding Tool")
  .version("0.1.0");

program
  .command("repl")
  .description("Start interactive REPL session")
  .option("--verbose", "Enable verbose logging of Think→Act→Observe iterations")
  .action(async (opts) => {
    const { ProviderRouter } = await import("@vector-code/core");
    const { printBanner, PROMPT } = await import("./ui/banner.js");
    const { App } = await import("./ui/App.js");
    const React = await import("react");
    const { render } = await import("ink");

    // Collect startup data
    const router = new ProviderRouter();
    const ollamaModels = await router.listOllamaModels();
    const vmdPath = process.cwd() + "/VECTOR.md";
    const { existsSync } = await import("fs");
    const hasVectorMd = existsSync(vmdPath);

    // Print banner before Ink renderer takes over
    console.clear();
    printBanner("vector-focus", ollamaModels, hasVectorMd);
    console.log(PROMPT);

    render(React.createElement(App, { verbose: !!opts.verbose }));
  });

program
  .command("run")
  .description("Run a one-shot task non-interactively")
  .argument("<task>", "Task description")
  .option("--verbose", "Enable verbose logging")
  .option("--timeout <ms>", "Tool call timeout in ms", "30000")
  .action(async (task, opts) => {
    const { AgenticLoop } = await import("@vector-code/core");
    const loop = new AgenticLoop({
      verbose: !!opts.verbose,
      toolTimeoutMs: parseInt(opts.timeout, 10),
    });
    const result = await loop.run(task);
    console.log(result);
    const iters = loop.getIterations();
    if (iters.length > 0) {
      console.error(`\n[Summary] ${iters.length} iterations:`);
      for (const i of iters) {
        const name = i.toolCall?.name ?? "(respond)";
        const dur = i.toolResult ? `${i.toolResult.durationMs}ms` : "";
        console.error(`  ${i.n}. ${name} ${dur}`);
      }
    }
  });

program
  .command("auto")
  .description("Run autonomous mode with continuous loop")
  .option("--verbose", "Enable verbose logging")
  .action(async (opts) => {
    const { AgenticLoop } = await import("@vector-code/core");
    console.log("Auto mode running (press Ctrl+C to stop)...");
    new AgenticLoop({ verbose: !!opts.verbose, maxIterations: 999_999 });
  });

program
  .command("status")
  .description("Show session status")
  .action(async () => {
    const { ProviderRouter, loadConfig } = await import("@vector-code/core");
    const router = new ProviderRouter();
    const config = loadConfig();
    console.log(`Vector Code v0.1.0`);
    const ollama = await router.checkProviderStatus("ollama");
    console.log(`Ollama: ${ollama === "online" ? "\x1b[92monline\x1b[0m" : "\x1b[93moffline\x1b[0m"}`);
    console.log(`Default model: ${config.defaults.model}`);
    const providers = ["anthropic","openai","google","groq","nvidia","github","ollama"];
    for (const p of providers) {
      const s = await router.checkProviderStatus(p);
      const dot = s === "online" ? "\u{1F7E2}" : s === "no-key" ? "\u{26AA}" : "\u{1F534}";
      console.log(`  ${dot} ${p}`);
    }
  });

program
  .command("models")
  .description("List all 60+ models across 17 providers (filter: provider name)")
  .argument("[provider]", "Filter by provider name (e.g. groq, anthropic)")
  .action(async (filter: string) => {
    const { cmdModels } = await import("@vector-code/core");
    await cmdModels(filter || undefined);
  });

program
  .command("apikey")
  .description("Set an API key for a provider")
  .argument("<provider>", "Provider name")
  .argument("<key>", "API key")
  .argument("[extra]", "Extra param (e.g. account ID for Cloudflare)")
  .action(async (provider, key, extra) => {
    const { cmdApiKey } = await import("@vector-code/core");
    const args = [provider, key, extra].filter((x): x is string => !!x);
    await cmdApiKey(args);
  });

program.parse(process.argv);
