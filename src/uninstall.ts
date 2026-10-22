// Decides which kind cluster uninstall may delete, and how doctor describes a lab that is already running
import { isBakeryClusterName } from "./lib/names.js";
import type { PreflightReport } from "./steps/preflight.js";

export type UninstallTarget = { target?: string; guessed?: boolean; error?: string };

// Never invent a name: a lost or stale state.json must not turn into deleting the wrong cluster or finding none
export function pickUninstallTarget(o: { stateName?: string; explicit?: string; clusters: string[] }): UninstallTarget {
  const stateLive = o.stateName !== undefined && o.clusters.includes(o.stateName);
  if (o.explicit) {
    if (!o.clusters.includes(o.explicit)) return { error: `No kind cluster named "${o.explicit}"` };
    if (!isBakeryClusterName(o.explicit)) return { error: `"${o.explicit}" is not a gitops-bakery cluster; delete it with kind if you mean to` };
    if (stateLive && o.stateName !== o.explicit)
      return { error: `This machine's lab is ${o.stateName}; --cluster ${o.explicit} would wipe its settings. Run uninstall without --cluster` };
    return { target: o.explicit };
  }
  if (stateLive) return { target: o.stateName };
  const candidates = o.clusters.filter(isBakeryClusterName);
  if (candidates.length === 1) return { target: candidates[0], guessed: true };
  if (candidates.length === 0) return { error: "No gitops-bakery cluster found" };
  return { error: `Several clusters look like gitops-bakery labs (${candidates.join(", ")}); pick one with --cluster <name>` };
}

export function doctorSummary(report: PreflightReport, runningCluster: string | undefined): string {
  if (!report.ok) return report.problems.map((p) => `✗ ${p}`).join("\n");
  if (runningCluster) return `✓ Lab ${runningCluster} is running; its ports are in use by it. See \`gitops-bakery status\`.`;
  return "✓ Ready to install";
}
