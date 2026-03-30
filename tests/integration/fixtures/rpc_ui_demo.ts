import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export default function (pi: ExtensionAPI) {
	pi.on("session_before_switch", async (event, ctx) => {
		if (event.reason !== "new" || !ctx.hasUI) return;

		const confirmed = await ctx.ui.confirm("Clear session?", "All messages will be lost.");
		if (!confirmed) {
			return { cancel: true };
		}
	});

	pi.registerCommand("rpc-select", {
		description: "Prompt for a deterministic select response in RPC mode",
		handler: async (_args, ctx) => {
			const choice = await ctx.ui.select("Pick a value", ["Allow", "Block"]);
			ctx.ui.notify(choice ? `select:${choice}` : "select:cancelled", "info");
		},
	});

	pi.registerCommand("rpc-input", {
		description: "Prompt for deterministic text input in RPC mode",
		handler: async (_args, ctx) => {
			const value = await ctx.ui.input("Enter a value", "type something...");
			ctx.ui.notify(value ? `input:${value}` : "input:cancelled", "info");
		},
	});

	pi.registerCommand("rpc-editor", {
		description: "Prompt for deterministic multi-line editor input in RPC mode",
		handler: async (_args, ctx) => {
			const text = await ctx.ui.editor("Edit some text", "Line 1\nLine 2\nLine 3");
			ctx.ui.notify(text ? `editor:${text.replace(/\n/g, "|")}` : "editor:cancelled", "info");
		},
	});

	pi.registerCommand("rpc-fire-and-forget", {
		description: "Emit all RPC-safe fire-and-forget UI requests in a deterministic order",
		handler: async (_args, ctx) => {
			ctx.ui.notify("fire:notify", "warning");
			ctx.ui.setStatus("rpc-demo", "fire:status");
			ctx.ui.setWidget("rpc-demo", ["--- RPC Demo ---", "fire:widget"], { placement: "belowEditor" });
			ctx.ui.setTitle("pi RPC Demo");
			ctx.ui.setEditorText("prefilled text for the user");
		},
	});
}
