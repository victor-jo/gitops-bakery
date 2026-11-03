// Builds the drift-detection component image (Evidently, MLflow) and pushes it next to the inference image in Harbor
import { assetPath } from "../../lib/paths.js";
import type { Step } from "../types.js";
import { pushLabImage } from "./kfp-image.js";

export const DRIFT_IMAGE = "drift-pipeline:0.1.0";

// A step of its own, so a lab whose KFP image step is already done still builds this image on its next install
export const mlDriftImageStep: Step = {
  id: "ml-drift-image",
  title: "Drift component image in Harbor",
  async run(ctx) {
    await pushLabImage(ctx, DRIFT_IMAGE, assetPath("labs", "ml", "drift", "pipeline", "src"));
  },
};
