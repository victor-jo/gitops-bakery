# Binary matrix factorization trained with BCE; plain dot product, not the reference's MLP head,
# because fold-in of a new user (a couple member's own marks) needs scores linear in the user vector.
import numpy as np
import pandas as pd
import torch
from torch import nn


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

    def forward(self, u: torch.Tensor, i: torch.Tensor) -> torch.Tensor:
        dot = (self.user_emb(u) * self.item_emb(i)).sum(-1)
        return dot + self.user_bias(u).squeeze(-1) + self.item_bias(i).squeeze(-1) + self.global_bias


def train(
    df: pd.DataFrame, n_users: int, n_items: int, dim: int = 32, epochs: int = 5,
    batch: int = 65536, lr: float = 0.01, weight_decay: float = 1e-5,
) -> MF:
    torch.manual_seed(0)
    model = MF(n_users, n_items, dim)
    u = torch.as_tensor(df["user_idx"].to_numpy(), dtype=torch.long)
    i = torch.as_tensor(df["item_idx"].to_numpy(), dtype=torch.long)
    y = torch.as_tensor(df["label"].to_numpy(), dtype=torch.float32)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    loss_fn = nn.BCEWithLogitsLoss()
    model.train()
    for _ in range(epochs):
        order = torch.randperm(len(y))
        for start in range(0, len(y), batch):
            idx = order[start:start + batch]
            opt.zero_grad()
            loss_fn(model(u[idx], i[idx]), y[idx]).backward()
            opt.step()
    model.eval()
    return model


def predict(model: MF, user_idx, item_idx) -> np.ndarray:
    """Like-probabilities for aligned user/item index arrays."""
    with torch.no_grad():
        logits = model(torch.as_tensor(user_idx, dtype=torch.long), torch.as_tensor(item_idx, dtype=torch.long))
    return torch.sigmoid(logits).numpy()


def export(model: MF) -> dict:
    """Float32 numpy parameters so scoring needs no torch at serving time."""
    def arr(t: torch.Tensor) -> np.ndarray:
        return t.detach().cpu().numpy().astype(np.float32)

    return {
        "item_vecs": arr(model.item_emb.weight),
        "item_bias": arr(model.item_bias.weight).reshape(-1),
        "global_bias": float(model.global_bias.item()),
        "user_vecs": arr(model.user_emb.weight),
        "user_bias": arr(model.user_bias.weight).reshape(-1),
    }
