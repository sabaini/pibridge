import {
	type Api,
	type AssistantMessage,
	type AssistantMessageEventStream,
	calculateCost,
	type Context,
	createAssistantMessageEventStream,
	type Model,
	type SimpleStreamOptions,
} from "@mariozechner/pi-ai";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

const MOCK_PROVIDER_NAME = "pi-rpc-mock";
const MOCK_MODEL_ID = "canned-responses";
const MOCK_API = "pi-rpc-mock-api" as Api;
const MOCK_API_KEY_ENV = "PI_RPC_MOCK_API_KEY";
const MOCK_PROMPT_MAP_ENV = "PI_RPC_MOCK_PROMPT_MAP";
const MOCK_CONTEXT_MAP_ENV = "PI_RPC_MOCK_CONTEXT_MAP";
const MISSING_RESPONSE_PREFIX = "[pi-rpc-mock missing canned response]";

export function getLastUserText(context: Context): string {
	for (let index = context.messages.length - 1; index >= 0; index -= 1) {
		const message = context.messages[index];
		if (message.role !== "user") continue;
		if (typeof message.content === "string") return message.content;
		return message.content
			.filter((block) => block.type === "text")
			.map((block) => block.text)
			.join("");
	}
	return "";
}

function loadResponseMap(envName: string): Record<string, string> {
	const raw = process.env[envName];
	if (!raw) return {};

	const parsed = JSON.parse(raw) as unknown;
	if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
		throw new Error(`${envName} must be a JSON object mapping keys to canned responses`);
	}

	const responseMap: Record<string, string> = {};
	for (const [key, response] of Object.entries(parsed)) {
		if (typeof response !== "string") {
			throw new Error(`${envName} values must be strings; got ${typeof response} for key ${JSON.stringify(key)}`);
		}
		responseMap[key] = response;
	}
	return responseMap;
}

export function loadPromptMap(): Record<string, string> {
	return loadResponseMap(MOCK_PROMPT_MAP_ENV);
}

export function loadContextMap(): Record<string, string> {
	return loadResponseMap(MOCK_CONTEXT_MAP_ENV);
}

function stableStringify(value: unknown): string {
	if (Array.isArray(value)) {
		return `[${value.map((item) => stableStringify(item)).join(",")}]`;
	}
	if (value && typeof value === "object") {
		const entries = Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right));
		return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${stableStringify(item)}`).join(",")}}`;
	}
	return JSON.stringify(value);
}

function textContentToString(content: string | Array<{ type: string; text?: string }>): string {
	if (typeof content === "string") return content;
	return content
		.filter((block) => block.type === "text")
		.map((block) => block.text ?? "")
		.join("");
}

function assistantContentToString(content: AssistantMessage["content"]): string {
	return content
		.map((block) => {
			if (block.type === "text") return block.text;
			if (block.type === "thinking") return `<thinking>${block.thinking}</thinking>`;
			return `<toolCall:${block.name}>${JSON.stringify(block.arguments)}`;
		})
		.join("");
}

function getSimplifiedMessages(context: Context): Array<Record<string, string>> {
	return context.messages.map((message) => {
		if (message.role === "user") {
			return { content: textContentToString(message.content), role: message.role };
		}
		if (message.role === "assistant") {
			return { content: assistantContentToString(message.content), role: message.role };
		}
		return { content: textContentToString(message.content), role: message.role, toolName: message.toolName };
	});
}

export function getContextKey(context: Context): string {
	return stableStringify(getSimplifiedMessages(context));
}

function getContextResponse(context: Context): string | undefined {
	const simplifiedMessages = getSimplifiedMessages(context);
	const entries = Object.entries(loadContextMap())
		.map(([serializedMessages, response]) => {
			const parsed = JSON.parse(serializedMessages) as unknown;
			if (!Array.isArray(parsed)) {
				throw new Error(`${MOCK_CONTEXT_MAP_ENV} keys must serialize message arrays`);
			}
			return { messages: parsed, response };
		})
		.sort((left, right) => right.messages.length - left.messages.length);
	for (const entry of entries) {
		if (entry.messages.length > simplifiedMessages.length) continue;
		const actualSuffix = simplifiedMessages.slice(-entry.messages.length);
		if (stableStringify(actualSuffix) === stableStringify(entry.messages)) {
			return entry.response;
		}
	}
	return undefined;
}

export function streamMockProvider(model: Model<Api>, context: Context, options?: SimpleStreamOptions): AssistantMessageEventStream {
	const stream = createAssistantMessageEventStream();

	void (async () => {
		const output: AssistantMessage = {
			role: "assistant",
			content: [],
			api: model.api,
			provider: model.provider,
			model: model.id,
			usage: {
				input: 0,
				output: 0,
				cacheRead: 0,
				cacheWrite: 0,
				totalTokens: 0,
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
			},
			stopReason: "stop",
			timestamp: Date.now(),
		};

		try {
			if (options?.signal?.aborted) {
				throw new Error("mock provider aborted before streaming started");
			}

			const prompt = getLastUserText(context);
			const responseText = getContextResponse(context) ?? loadPromptMap()[prompt] ?? `${MISSING_RESPONSE_PREFIX} ${prompt}`;

			stream.push({ type: "start", partial: output });
			output.content.push({ type: "text", text: "" });
			const contentIndex = output.content.length - 1;
			stream.push({ type: "text_start", contentIndex, partial: output });

			if (responseText.length > 0) {
				if (options?.signal?.aborted) {
					throw new Error("mock provider aborted during streaming");
				}
				const block = output.content[contentIndex];
				if (block.type !== "text") {
					throw new Error("mock provider expected text content block");
				}
				block.text += responseText;
				output.usage.output = responseText.length;
				output.usage.totalTokens = output.usage.input + output.usage.output;
				calculateCost(model, output.usage);
				stream.push({ type: "text_delta", contentIndex, delta: responseText, partial: output });
			}

			stream.push({ type: "text_end", contentIndex, content: responseText, partial: output });
			stream.push({ type: "done", reason: output.stopReason, message: output });
			stream.end();
		} catch (error) {
			output.stopReason = options?.signal?.aborted ? "aborted" : "error";
			output.errorMessage = error instanceof Error ? error.message : String(error);
			stream.push({ type: "error", reason: output.stopReason, error: output });
			stream.end();
		}
	})();

	return stream;
}

export default function (pi: ExtensionAPI) {
	pi.registerProvider(MOCK_PROVIDER_NAME, {
		baseUrl: "mock://pi-rpc-provider",
		apiKey: MOCK_API_KEY_ENV,
		api: MOCK_API,
		models: [
			{
				id: MOCK_MODEL_ID,
				name: "Canned Responses",
				reasoning: false,
				input: ["text"],
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
				contextWindow: 16384,
				maxTokens: 4096,
			},
		],
		streamSimple: streamMockProvider,
	});
}
