import React, { useEffect, useState } from "react";
import { Box, Text } from "ink";
import { ProviderRouter, MODEL_REGISTRY, ProviderHealth } from "@vector-code/core";

interface ModelsTableProps {
  activeModel: string;
}

interface Row {
  provider: string;
  models: string;
  modelCount: number;
  status: string;
  contextWindow: string;
  tools: string;
  reachable: boolean;
  isActive: boolean;
}

export function ModelsTable({ activeModel }: ModelsTableProps) {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const router = new ProviderRouter();
    const uniqueProviders = [...new Set(MODEL_REGISTRY.map(m => m.provider))];

    const checks = uniqueProviders.map(async (provider) => {
      const status = await router.checkProviderStatus(provider);
      const providerModels = MODEL_REGISTRY.filter(m => m.provider === provider);
      const isActive = providerModels.some(m => m.id === activeModel)
        || provider === activeModel.split("/")[0];
      return {
        provider,
        models: providerModels.slice(0, 3).map(m => m.displayName).join(", ") + (providerModels.length > 3 ? "..." : ""),
        modelCount: providerModels.length,
        status: status === "online" ? "\u{1F7E2}" : status === "no-key" ? "\u{26AA}" : "\u{1F534}",
        contextWindow: providerModels.length > 0
          ? `${(providerModels[0].contextWindow / 1000).toFixed(0)}K`
          : "—",
        tools: providerModels.some(m => m.supportsTools) ? "yes" : "no",
        reachable: status === "online",
        isActive,
      };
    });

    Promise.all(checks).then(results => {
      setRows(results);
      setLoading(false);
    });
  }, [activeModel]);

  if (loading) {
    return <Text dimColor>Checking 17 providers...</Text>;
  }

  return (
    <Box flexDirection="column" paddingX={1}>
      <Box borderStyle="single" borderColor="cyan" flexDirection="column" paddingX={1}>
        <Box>
          <Box width={3}><Text bold color="cyan">{""}</Text></Box>
          <Box width={14}><Text bold color="cyan">PROVIDER</Text></Box>
          <Box width={36}><Text bold color="cyan">MODELS</Text></Box>
          <Box width={3}><Text bold color="cyan">ST</Text></Box>
          <Box width={8}><Text bold color="cyan">CONTEXT</Text></Box>
          <Box width={6}><Text bold color="cyan">TOOLS</Text></Box>
        </Box>
        <Text dimColor>{"─".repeat(70)}</Text>

        {rows.map((r, i) => (
          <Box key={i}>
            <Box width={3}>
              {r.isActive && <Text color="cyan">{"\u25B6"}</Text>}
            </Box>
            <Box width={14}>
              {r.isActive
                ? <Text color="cyan" bold>{r.provider}</Text>
                : <Text dimColor>{r.provider}</Text>
              }
            </Box>
            <Box width={36}>
              {r.isActive
                ? <Text bold>{r.models.slice(0, 34)}</Text>
                : <Text>{r.models.slice(0, 34)}</Text>
              }
            </Box>
            <Box width={3}>
              <Text>{r.status}</Text>
            </Box>
            <Box width={8}>
              <Text>{r.contextWindow}</Text>
            </Box>
            <Box width={6}>
              <Text color={r.tools === "yes" ? "green" : "red"}>{r.tools}</Text>
            </Box>
          </Box>
        ))}
      </Box>
      <Text dimColor>  {"\u{1F7E2}"} online  {"\u{26AA}"} no key  {"\u{1F534}"} offline  {"\u25B6"} active model</Text>
      <Text dimColor>  Set keys via: /apikey {"<"}provider{">"} {"<"}key{">"}</Text>
    </Box>
  );
}
