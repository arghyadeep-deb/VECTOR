import { parseToolArguments } from "./request-parsing.js";
import { handleApiError } from "./utils.js";
/**
 * Creates a standardized tool with consistent error handling and structure
 * Eliminates the need for repetitive tool definition boilerplate
 */
export function createTool(config, handlerFn) {
    const definition = {
        name: config.name,
        description: config.description,
        inputSchema: {
            type: "object",
            properties: config.properties,
            required: config.required || [],
        },
        ...(config.annotations && { annotations: config.annotations }),
    };
    const handler = async (request) => {
        try {
            const args = parseToolArguments(request, config.schema);
            return await handlerFn(args);
        }
        catch (error) {
            handleApiError(error, config.name);
        }
    };
    return {
        definition,
        handler,
        schema: config.schema,
    };
}
/**
 * Creates a simple text response for tools
 */
export function createTextResponse(text) {
    return {
        content: [
            {
                type: "text",
                text,
            },
        ],
    };
}
/**
 * Creates a formatted list response for tools
 */
export function createListResponse(items, title) {
    const text = title ? `${title}\n\n${items.join("\n")}` : items.join("\n");
    return createTextResponse(text);
}
/**
 * Creates an error response with consistent formatting
 */
export function createErrorResponse(error, context) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    return createTextResponse(`Error in ${context}: ${errorMsg}`);
}
