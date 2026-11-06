# Binary matrix factorization trained with BCE; plain dot product, not the reference's MLP head,
# because fold-in of a new user (a couple member's own marks) needs scores linear in the user vector.
import numpy as np
import pandas as pd
import torch
from torch import nn

PREDICT_BATCH = 1_000_000


class MF(nn.Module):
    """logit(u, i) = user_vec[u] . item_vec[i] + user_bias[u] + item_bias[i] + global_bias."""

    def __init__(self, n_users: int, n_items: int, dim: int = 32):
        super().__init__()
        self.user_emb = nn.Embedding(n_users, dim)
        self.item_emb = nn.Embedding(n_items, dim)
        self.user_bias = nn.Embedding(n_users, 1)
        self.item_bias = nn.Embedding(n_items, 1)
        self.global_bias = nn.Parameter(torch.zeros(1))
        nn.init.normal_(self.user_emb.weight, std=0.1)
        nn.init.normal_(self.item_emb.weight, std=0.1)
        nn.init.zeros_(self.user_bias.weight)
        nn.init.zeros_(self.item_bias.weight)

    def item_terms(self, i: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Vector and bias of items i."""
        return self.item_emb(i), self.item_bias(i).squeeze(-1)

    def forward(self, u: torch.Tensor, i: torch.Tensor) -> torch.Tensor:
        item_vec, item_bias = self.item_terms(i)
        dot = (self.user_emb(u) * item_vec).sum(-1)
        return dot + self.user_bias(u).squeeze(-1) + item_bias + self.global_bias


class HybridMF(MF):
    """MF whose item vector and bias add a learned linear map of fixed item features to the id terms.

    item_vec[i] = item_emb[i] + W f[i] and item_bias[i] = b[i] + w . f[i]; the score stays linear in the
    user vector, so a viewer folds in against the exported item vectors exactly as with the plain MF.
    """

    def __init__(self, n_users: int, n_items: int, features: np.ndarray, dim: int = 32):
        super().__init__(n_users, n_items, dim)
        self.register_buffer("features", torch.as_tensor(features, dtype=torch.float32))
        self.feature_vec = nn.Linear(features.shape[1], dim, bias=False)
        self.feature_bias = nn.Linear(features.shape[1], 1, bias=False)
        # Zero start: training begins from the plain MF and learns what the features add
        nn.init.zeros_(self.feature_vec.weight)
        nn.init.zeros_(self.feature_bias.weight)

    def item_terms(self, i: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        item_vec, item_bias = super().item_terms(i)
        f = self.features[i]
        return item_vec + self.feature_vec(f), item_bias + self.feature_bias(f).squeeze(-1)


def train(
    df: pd.DataFrame, n_users: int, n_items: int, dim: int = 32, epochs: int = 5,
    # No L2 by default: Adam's weight decay pulled the item vectors onto one popularity axis
    batch: int = 65536, lr: float = 0.01, weight_decay: float = 0.0,
    item_features: np.ndarray | None = None,
) -> MF:
    """Fit by BCE on (user_idx, item_idx, label) rows; item_features (one row per item) trains a HybridMF."""
    torch.manual_seed(0)
    model = MF(n_users, n_items, dim) if item_features is None else HybridMF(n_users, n_items, item_features, dim)
    u = torch.from_numpy(df["user_idx"].to_numpy())
    i = torch.from_numpy(df["item_idx"].to_numpy())
    y = torch.from_numpy(df["label"].to_numpy(dtype="float32"))
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    loss_fn = nn.BCEWithLogitsLoss()
    model.train()
    for _ in range(epochs):
        order = torch.randperm(len(y))
        for start in range(0, len(y), batch):
            idx = order[start:start + batch]
            opt.zero_grad()
            loss_fn(model(u[idx].long(), i[idx].long()), y[idx]).backward()
            opt.step()
    model.eval()
    return model


def predict(model: MF, user_idx, item_idx) -> np.ndarray:
    """Like-probabilities for aligned user/item index arrays."""
    user_idx, item_idx = np.asarray(user_idx), np.asarray(item_idx)
    out = np.empty(len(user_idx), dtype=np.float32)
    with torch.no_grad():
        for s in range(0, len(out), PREDICT_BATCH):
            u = torch.from_numpy(user_idx[s:s + PREDICT_BATCH]).long()
            i = torch.from_numpy(item_idx[s:s + PREDICT_BATCH]).long()
            out[s:s + PREDICT_BATCH] = torch.sigmoid(model(u, i)).numpy()
    return out


def export(model: MF) -> dict:
    """Float32 numpy parameters so scoring needs no torch at serving time.

    A HybridMF exports its full item vectors and biases (id plus feature terms), so the layout is the same.
    """
    def arr(t: torch.Tensor) -> np.ndarray:
        return t.detach().cpu().numpy().astype(np.float32)

    with torch.no_grad():
        item_vecs, item_bias = model.item_terms(torch.arange(model.item_emb.num_embeddings))
    return {
        "item_vecs": arr(item_vecs),
        "item_bias": arr(item_bias),
        "global_bias": float(model.global_bias.item()),
        "user_vecs": arr(model.user_emb.weight),
        "user_bias": arr(model.user_bias.weight).reshape(-1),
    }
