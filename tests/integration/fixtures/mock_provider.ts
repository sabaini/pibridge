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

export type MockResponseSpec =
	| string
	| {
		attempts?: MockResponseSpec[];
		chunks?: string[];
		delayMs?: number;
		errorAfterChunks?: number;
		errorMessage?: string;
		initialDelayMs?: number;
		text?: string;
		waitForAbort?: boolean;
	};

const promptAttemptCounters = new Map<string, number>();
const contextAttemptCounters = new Map<string, number>();

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

function isMockResponseSpec(value: unknown): value is MockResponseSpec {
	if (typeof value === "string") return true;
	if (!value || typeof value !== "object" || Array.isArray(value)) return false;
	const candidate = value as Record<string, unknown>;
	if (candidate.text !== undefined && typeof candidate.text !== "string") return false;
	if (candidate.delayMs !== undefined && typeof candidate.delayMs !== "number") return false;
	if (candidate.initialDelayMs !== undefined && typeof candidate.initialDelayMs !== "number") return false;
	if (candidate.errorAfterChunks !== undefined && typeof candidate.errorAfterChunks !== "number") return false;
	if (candidate.errorMessage !== undefined && typeof candidate.errorMessage !== "string") return false;
	if (candidate.waitForAbort !== undefined && typeof candidate.waitForAbort !== "boolean") return false;
	if (candidate.chunks !== undefined) {
		if (!Array.isArray(candidate.chunks) || !candidate.chunks.every((chunk) => typeof chunk === "string")) return false;
	}
	if (candidate.attempts !== undefined) {
		if (!Array.isArray(candidate.attempts) || !candidate.attempts.every((attempt) => isMockResponseSpec(attempt))) return false;
	}
	return true;
}

function loadResponseMap(envName: string): Record<string, MockResponseSpec> {
	const raw = process.env[envName];
	if (!raw) return {};

	const parsed = JSON.parse(raw) as unknown;
	if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
		throw new Error(`${envName} must be a JSON object mapping keys to canned responses`);
	}

	const responseMap: Record<string, MockResponseSpec> = {};
	for (const [key, response] of Object.entries(parsed)) {
		if (!isMockResponseSpec(response)) {
			throw new Error(`${envName} values must be strings or supported mock response objects; got ${typeof response} for key ${JSON.stringify(key)}`);
		}
		responseMap[key] = response;
	}
	return responseMap;
}

export function loadPromptMap(): Record<string, MockResponseSpec> {
	return loadResponseMap(MOCK_PROMPT_MAP_ENV);
}

export function loadContextMap(): Record<string, MockResponseSpec> {
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

function selectAttemptedResponse(
	key: string,
	response: MockResponseSpec,
	counterMap: Map<string, number>,
): Exclude<MockResponseSpec, string> | string {
	if (typeof response === "string") return response;
	if (!response.attempts || response.attempts.length === 0) return response;
	const attemptIndex = counterMap.get(key) ?? 0;
	counterMap.set(key, attemptIndex + 1);
	return response.attempts[Math.min(attemptIndex, response.attempts.length - 1)];
}

function getContextResponse(context: Context): MockResponseSpec | undefined {
	const simplifiedMessages = getSimplifiedMessages(context);
	const entries = Object.entries(loadContextMap())
		.map(([serializedMessages, response]) => {
			const parsed = JSON.parse(serializedMessages) as unknown;
			if (!Array.isArray(parsed)) {
				throw new Error(`${MOCK_CONTEXT_MAP_ENV} keys must serialize message arrays`);
			}
			return { key: serializedMessages, messages: parsed, response };
		})
		.sort((left, right) => right.messages.length - left.messages.length);
	for (const entry of entries) {
		if (entry.messages.length > simplifiedMessages.length) continue;
		const actualSuffix = simplifiedMessages.slice(-entry.messages.length);
		if (stableStringify(actualSuffix) === stableStringify(entry.messages)) {
			return selectAttemptedResponse(entry.key, entry.response, contextAttemptCounters);
		}
	}
	return undefined;
}

function getPromptResponse(prompt: string): MockResponseSpec | undefined {
	const response = loadPromptMap()[prompt];
	if (response === undefined) return undefined;
	return selectAttemptedResponse(prompt, response, promptAttemptCounters);
}

function normalizeResponseSpec(spec: MockResponseSpec, prompt: string): Required<Omit<Exclude<MockResponseSpec, string>, "attempts">> {
	if (typeof spec === "string") {
		return {
			chunks: spec.length > 0 ? [spec] : [],
			delayMs: 0,
			errorAfterChunks: -1,
			errorMessage: "",
			initialDelayMs: 0,
			text: spec,
			waitForAbort: false,
		};
	}
	const text = spec.text ?? (spec.chunks ? spec.chunks.join("") : `${MISSING_RESPONSE_PREFIX} ${prompt}`);
	return {
		chunks: spec.chunks ?? (text.length > 0 ? [text] : []),
		delayMs: spec.delayMs ?? 0,
		errorAfterChunks: spec.errorAfterChunks ?? -1,
		errorMessage: spec.errorMessage ?? "mock provider configured failure",
		initialDelayMs: spec.initialDelayMs ?? 0,
		text,
		waitForAbort: spec.waitForAbort ?? false,
	};
}

function sleep(delayMs: number, signal?: AbortSignal): Promise<void> {
	if (delayMs <= 0) return Promise.resolve();
	return new Promise<void>((resolve, reject) => {
		const timer = setTimeout(() => {
			signal?.removeEventListener("abort", onAbort);
			resolve();
		}, delayMs);
		const onAbort = () => {
			clearTimeout(timer);
			reject(new Error("mock provider aborted during streaming"));
		};
		signal?.addEventListener("abort", onAbort, { once: true });
	});
}

async function waitForAbort(signal?: AbortSignal): Promise<void> {
	if (!signal) {
		while (true) {
			await sleep(100);
		}
	}
	if (signal.aborted) {
		throw new Error("mock provider aborted during streaming");
	}
	await new Promise<void>((_, reject) => {
		signal.addEventListener("abort", () => reject(new Error("mock provider aborted during streaming")), { once: true });
	});
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
			const selectedSpec = getContextResponse(context) ?? getPromptResponse(prompt) ?? `${MISSING_RESPONSE_PREFIX} ${prompt}`;
			const response = normalizeResponseSpec(selectedSpec, prompt);

			stream.push({ type: "start", partial: output });
			output.content.push({ type: "text", text: "" });
			const contentIndex = output.content.length - 1;
			stream.push({ type: "text_start", contentIndex, partial: output });

			if (response.initialDelayMs > 0) {
				await sleep(response.initialDelayMs, options?.signal);
			}

			let emittedChunks = 0;
			for (const chunk of response.chunks) {
				if (emittedChunks > 0 && response.delayMs > 0) {
					await sleep(response.delayMs, options?.signal);
				}
				if (options?.signal?.aborted) {
					throw new Error("mock provider aborted during streaming");
				}
				const block = output.content[contentIndex];
				if (block.type !== "text") {
					throw new Error("mock provider expected text content block");
				}
				block.text += chunk;
				emittedChunks += 1;
				output.usage.output = block.text.length;
				output.usage.totalTokens = output.usage.input + output.usage.output;
				calculateCost(model, output.usage);
				stream.push({ type: "text_delta", contentIndex, delta: chunk, partial: output });
				if (response.errorAfterChunks >= 0 && emittedChunks >= response.errorAfterChunks) {
					throw new Error(response.errorMessage);
				}
			}

			if (response.waitForAbort) {
				await waitForAbort(options?.signal);
			}

			stream.push({ type: "text_end", contentIndex, content: response.text, partial: output });
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
