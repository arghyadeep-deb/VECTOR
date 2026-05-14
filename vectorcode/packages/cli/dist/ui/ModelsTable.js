import React, { useEffect, useState } from "react";
import { Box, Text } from "ink";
import { ProviderRouter, MODEL_REGISTRY } from "@vector-code/core";
export function ModelsTable({ activeModel }) {
    const [rows, setRows] = useState([]);
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
        return React.createElement(Text, { dimColor: true }, "Checking 17 providers...");
    }
    return (React.createElement(Box, { flexDirection: "column", paddingX: 1 },
        React.createElement(Box, { borderStyle: "single", borderColor: "cyan", flexDirection: "column", paddingX: 1 },
            React.createElement(Box, null,
                React.createElement(Box, { width: 3 },
                    React.createElement(Text, { bold: true, color: "cyan" }, "")),
                React.createElement(Box, { width: 14 },
                    React.createElement(Text, { bold: true, color: "cyan" }, "PROVIDER")),
                React.createElement(Box, { width: 36 },
                    React.createElement(Text, { bold: true, color: "cyan" }, "MODELS")),
                React.createElement(Box, { width: 3 },
                    React.createElement(Text, { bold: true, color: "cyan" }, "ST")),
                React.createElement(Box, { width: 8 },
                    React.createElement(Text, { bold: true, color: "cyan" }, "CONTEXT")),
                React.createElement(Box, { width: 6 },
                    React.createElement(Text, { bold: true, color: "cyan" }, "TOOLS"))),
            React.createElement(Text, { dimColor: true }, "─".repeat(70)),
            rows.map((r, i) => (React.createElement(Box, { key: i },
                React.createElement(Box, { width: 3 }, r.isActive && React.createElement(Text, { color: "cyan" }, "\u25B6")),
                React.createElement(Box, { width: 14 }, r.isActive
                    ? React.createElement(Text, { color: "cyan", bold: true }, r.provider)
                    : React.createElement(Text, { dimColor: true }, r.provider)),
                React.createElement(Box, { width: 36 }, r.isActive
                    ? React.createElement(Text, { bold: true }, r.models.slice(0, 34))
                    : React.createElement(Text, null, r.models.slice(0, 34))),
                React.createElement(Box, { width: 3 },
                    React.createElement(Text, null, r.status)),
                React.createElement(Box, { width: 8 },
                    React.createElement(Text, null, r.contextWindow)),
                React.createElement(Box, { width: 6 },
                    React.createElement(Text, { color: r.tools === "yes" ? "green" : "red" }, r.tools)))))),
        React.createElement(Text, { dimColor: true },
            "  ",
            "\u{1F7E2}",
            " online  ",
            "\u{26AA}",
            " no key  ",
            "\u{1F534}",
            " offline  ",
            "\u25B6",
            " active model"),
        React.createElement(Text, { dimColor: true },
            "  Set keys via: /apikey ",
            "<",
            "provider",
            ">",
            " ",
            "<",
            "key",
            ">")));
}
//# sourceMappingURL=ModelsTable.js.map