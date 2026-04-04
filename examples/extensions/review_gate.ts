import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export default function (pi: ExtensionAPI) {
	pi.registerCommand("review-gate", {
		description: "Demo a realistic RPC-safe human approval flow for code review",
		handler: async (_args, ctx) => {
			ctx.ui.setTitle("pi RPC Review Gate");
			ctx.ui.setStatus("review-gate", "collecting review inputs");
			ctx.ui.setWidget("review-gate", ["--- Review Gate ---", "Preparing review options..."], {
				placement: "belowEditor",
			});
			ctx.ui.notify("review gate started", "info");

			const reviewMode = await ctx.ui.select("Pick a review mode", ["correctness", "security", "full"]);
			if (!reviewMode) {
				ctx.ui.notify("review gate cancelled before a mode was selected", "warning");
				return;
			}

			ctx.ui.setStatus("review-gate", `selected mode: ${reviewMode}`);
			const confirmed = await ctx.ui.confirm("Run the review gate?", `Selected mode: ${reviewMode}`);
			if (!confirmed) {
				ctx.ui.notify(`review gate cancelled for mode ${reviewMode}`, "warning");
				return;
			}

			const branchLabel = await ctx.ui.input("Branch / ticket label", "feature/extension-ui-rpc-support");
			if (!branchLabel) {
				ctx.ui.notify("review gate cancelled before a branch label was provided", "warning");
				return;
			}

			const additionalInstructions = await ctx.ui.editor(
				"Additional review instructions",
				`Focus on ${reviewMode} risks and provide concrete findings.`,
			);
			if (additionalInstructions === undefined) {
				ctx.ui.notify("review gate cancelled before the final prompt was prepared", "warning");
				return;
			}

			const preparedPrompt = [
				`Please run the ${reviewMode} review for ${branchLabel}.`,
				"",
				additionalInstructions,
			].join("\n");

			ctx.ui.setWidget(
				"review-gate",
				["--- Review Gate ---", `mode: ${reviewMode}`, `branch: ${branchLabel}`],
				{ placement: "belowEditor" },
			);
			ctx.ui.setStatus("review-gate", "prefilled next prompt");
			ctx.ui.setEditorText(preparedPrompt);
			ctx.ui.notify(`review gate prepared a prompt for ${branchLabel}`, "info");
		},
	});
}
