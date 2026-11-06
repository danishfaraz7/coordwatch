"""All tunable thresholds in one place so they can be defended (and tuned) in the demo."""
from dataclasses import dataclass, asdict


@dataclass
class Config:
    # --- narratives -------------------------------------------------------
    narrative_sim: float = 0.20        # cosine needed to join an existing narrative cluster
    narrative_merge_sim: float = 0.30  # centroids closer than this are merged
    min_narrative_size: int = 4        # smaller clusters are folded into "other"
    # --- near-duplicate text ---------------------------------------------
    dup_jaccard: float = 0.70          # 3-word-shingle Jaccard for "near identical"
    min_tokens_for_dup: int = 4        # ignore "lol", "wow", very short posts
    max_dup_authors: int = 150         # cap pair enumeration per duplicate cluster
    # --- coordination signals -------------------------------------------
    sync_window_s: int = 300           # "within minutes of each other"
    sync_sim: float = 0.55             # content similarity needed for a sync event
    min_shared_dup: int = 2            # distinct duplicated texts two accounts must share (strong)
    min_sync_events: int = 3           # distinct synchronous post-pairs (strong)
    min_amplify: int = 3               # reshares between two accounts (strong)
    created_window_h: int = 72         # accounts created within N hours of each other ...
    created_recent_days: int = 120     # ... AND both created < N days before their first post in the data (fresh accounts)
    sync_topic_sim: float = 0.25       # looser similarity accepted when the two posts are also in the same narrative
    sync_topic_window_s: int = 120     # ... but only if they are this close together
    avatar_hamming: int = 6            # max Hamming distance (of 64 bits) to call avatars "the same"
    default_avatar_share: float = 0.15 # a hash used by >15% of accounts is treated as a default avatar
    min_group_size: int = 3
    discount_verified: bool = False    # ignore verified accounts as coordination evidence (reduces FPs on news outlets)

    def to_dict(self):
        return asdict(self)
