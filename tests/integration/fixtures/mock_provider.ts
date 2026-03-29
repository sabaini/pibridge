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

export function loadPromptMap(): Record<string, string> {
	const raw = process.env[MOCK_PROMPT_MAP_ENV];
	if (!raw) return {};

	const parsed = JSON.parse(raw) as unknown;
	if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
		throw new Error(`${MOCK_PROMPT_MAP_ENV} must be a JSON object mapping prompts to canned responses`);
	}

	const promptMap: Record<string, string> = {};
	for (const [prompt, response] of Object.entries(parsed)) {
		if (typeof response !== "string") {
			throw new Error(`${MOCK_PROMPT_MAP_ENV} values must be strings; got ${typeof response} for prompt ${JSON.stringify(prompt)}`);
		}
		promptMap[prompt] = response;
	}
	return promptMap;
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
			const responseText = loadPromptMap()[prompt] ?? `${MISSING_RESPONSE_PREFIX} ${prompt}`;

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
