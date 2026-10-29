#!/usr/bin/env bash
# Re-renders the vendored Kubeflow Pipelines manifests for a new KFP version; review the diff, then re-pin metadata-writer by hand
set -euo pipefail
VERSION="${1:-2.18.0}"
OUT="$(cd "$(dirname "$0")/.." && pwd)/assets/gitops/platform-ml/kfp/manifests"
BASE="github.com/kubeflow/pipelines/manifests/kustomize"

{
  echo "# Kubeflow Pipelines $VERSION cluster-scoped resources (namespace, CRDs), rendered from manifests/kustomize/cluster-scoped-resources"
  kubectl kustomize "$BASE/cluster-scoped-resources?ref=$VERSION"
} > "$OUT/00-cluster-scoped.yaml"
{
  echo "# Kubeflow Pipelines $VERSION standalone install, rendered from manifests/kustomize/env/platform-agnostic"
  kubectl kustomize "$BASE/env/platform-agnostic?ref=$VERSION"
} > "$OUT/10-platform-agnostic.yaml"

# kfp-metadata-writer is published for amd64 only, and arm64 nodes refuse the image index with "no match for platform".
# Pin its amd64 manifest by digest (Rosetta runs it), as the current file does above the metadata-writer image line:
echo "Rendered $VERSION into $OUT"
echo "Next: replace the metadata-writer image with its amd64 digest, for example"
echo "  docker buildx imagetools inspect ghcr.io/kubeflow/kfp-metadata-writer:$VERSION"
