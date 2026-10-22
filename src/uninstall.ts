// Decides which kind cluster uninstall may delete, and how doctor describes a lab that is already running
import { isBakeryClusterName } from "./lib/names.js";
import type { PreflightReport } from "./steps/preflight.js";

export type UninstallTarget = { target?: string; guessed?: boolean; error?: string };

// Never invent a name: a lost state.json must not turn into deleting the wrong cluster or finding none
export function pickUninstallTarget(o: { stateName?: string; explicit?: string; clusters: string[] }): UninstallTarget {
  if (o.explicit) return o.clusters.includes(o.explicit) ? { target: o.explicit } : { error: `No kind cluster named "${o.explicit}"` };
  if (o.stateName) return { target: o.stateName };
  const candidates = o.clusters.filter(isBakeryClusterName);
  if (candidates.length === 1) return { target: candidates[0], guessed: true };
  if (candidates.length === 0) return { error: "No gitops-bakery cluster found (state.json is missing and no cluster has a bakery name)" };
  return { error: `Several clusters look like gitops-bakery labs (${candidates.join(", ")}); pick one with --cluster <name>` };
}

export function doctorSummary(report: PreflightReport, runningCluster: string | undefined): string {
  if (!report.ok) return report.problems.map((p) => `✗ ${p}`).join("\n");
  if (runningCluster) return `✓ Lab ${runningCluster} is running; its ports are in use by it. See \`gitops-bakery status\`.`;
  return "✓ Ready to install";
}
