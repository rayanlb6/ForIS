"""
SGATS: Similarity-Guided Automatic Test Selection
Implementation of Algorithm 3.1 from thesis
"""
import numpy as np
from typing import List, Set, Tuple
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'kimvieware-shared' / 'src'))
from kimvieware_shared.models import Trajectory


class SGATS:
    """
    Similarity-Guided Automatic Test Selection

    Reduces trajectory set T to Tred while preserving coverage.

    Key formulas (from thesis):

    1. Priority function (Equation 3.1):
       ρ(t) = α·cost(t) + β·|branches(t)| + γ·length(t)

    2. Similarity function (Equation 3.2):
       sim(ti, tj) = |branches(ti) ∩ branches(tj)| / |branches(ti) ∪ branches(tj)|

    3. Fusion criterion:
       Merge ti and tj if sim(ti, tj) > θ (threshold)
    """

    def __init__(
        self,
        alpha: float = 0.4,   # Cost weight
        beta: float = 0.3,    # Coverage weight
        gamma: float = 0.3,   # Length weight
        similarity_threshold: float = 0.6
    ):
        self.alpha = alpha
        self.beta  = beta
        self.gamma = gamma
        self.theta = similarity_threshold

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def reduce(self, trajectories: List[Trajectory]) -> Tuple[List[Trajectory], dict]:
        """
        Main SGATS reduction algorithm.

        Args:
            trajectories: Initial trajectory set T

        Returns:
            (reduced_set, statistics)
        """
        print(f"\n{'='*60}")
        print(f"🔬 SGATS: Similarity-Guided Test Selection")
        print(f"{'='*60}")
        print(f"Input: |T| = {len(trajectories)} trajectories")

        # ── Detect degenerate inputs ──────────────────────────────────────
        branches_mode = self._detect_branches_mode(trajectories)

        # ── Step 1: priorities ────────────────────────────────────────────
        print(f"\n📊 Step 1: Calculating priorities (ρ)...")
        priorities = self._calculate_priorities(trajectories)
        print(f"   Priority range: [{priorities.min():.3f}, {priorities.max():.3f}]")

        if branches_mode == "empty":
            print(f"\n⚠️  WARNING: branches_covered is EMPTY for all trajectories.")
            print(f"   This is a deserialization problem (Trajectory.from_dict).")
            print(f"   Falling back to priority-only selection (no similarity fusion).")

        # ── Step 2: sort by priority ──────────────────────────────────────
        sorted_indices      = np.argsort(priorities)[::-1]
        sorted_trajectories = [trajectories[i] for i in sorted_indices]

        print(f"\n🔀 Step 2: Greedy selection with fusion (θ={self.theta})...")

        # ── Step 3: greedy selection ──────────────────────────────────────
        if branches_mode == "empty":
            # branches_covered is broken → skip coverage-based logic entirely,
            # select all trajectories ordered by priority (no fusion possible)
            reduced_set      = sorted_trajectories
            covered_branches = set()
            print(f"   [FALLBACK MODE] All {len(reduced_set)} trajectories kept "
                  f"(priority order, no coverage filtering).")
        else:
            reduced_set, covered_branches = self._greedy_selection(sorted_trajectories)

        # ── Step 4: statistics ────────────────────────────────────────────
        total_branches   = self._get_all_branches(trajectories)
        covered_branches = self._get_all_branches(reduced_set)

        cost_original = sum(t.cost for t in trajectories)
        cost_reduced  = sum(t.cost for t in reduced_set)

        stats = {
            'initial_count':    len(trajectories),
            'reduced_count':    len(reduced_set),
            'reduction_rate':   1 - (len(reduced_set) / len(trajectories)) if trajectories else 0,
            'total_branches':   len(total_branches),
            'covered_branches': list(covered_branches),
            'coverage_rate':    (len(covered_branches) / len(total_branches)
                                 if total_branches else 1.0),
            'initial_cost':     cost_original,
            'reduced_cost':     cost_reduced,
            'cost_reduction':   (1 - cost_reduced / cost_original
                                 if cost_original > 0 else 0.0),
            'branches_mode':    branches_mode,
        }

        print(f"\n✅ SGATS Results:")
        print(f"   |T| = {stats['initial_count']} → |Tred| = {stats['reduced_count']}")
        print(f"   Reduction: {stats['reduction_rate']*100:.1f}%")
        print(f"   Coverage:  {stats['coverage_rate']*100:.1f}%")
        print(f"   Cost reduction: {stats['cost_reduction']*100:.1f}%")
        print(f"   Branches mode:  {branches_mode}")
        print(f"{'='*60}\n")

        return reduced_set, stats

    # ──────────────────────────────────────────────────────────────────────
    # Core algorithm steps
    # ──────────────────────────────────────────────────────────────────────

    def _calculate_priorities(self, trajectories: List[Trajectory]) -> np.ndarray:
        """
        ρ(t) = α·cost(t) + β·|branches(t)| + γ·length(t)   (Eq 3.1)

        Each component is first normalized to [0, 1] independently so that
        the three terms are comparable regardless of their absolute magnitudes.
        """
        n = len(trajectories)

        costs    = np.array([t.cost              for t in trajectories], dtype=float)
        branches = np.array([len(t.branches_covered) for t in trajectories], dtype=float)
        lengths  = np.array([len(t.basic_blocks) for t in trajectories], dtype=float)

        # Per-component min-max normalization (avoid division by zero)
        def norm(arr: np.ndarray) -> np.ndarray:
            lo, hi = arr.min(), arr.max()
            return (arr - lo) / (hi - lo) if hi > lo else np.ones(n)

        priorities = (
            self.alpha * norm(costs)    +
            self.beta  * norm(branches) +
            self.gamma * norm(lengths)
        )

        # Global normalization to [0, 1]
        if priorities.max() > 0:
            priorities /= priorities.max()

        return priorities

    def _calculate_similarity(self, ti: Trajectory, tj: Trajectory) -> float:
        """
        Jaccard similarity (Eq 3.2):
        sim(ti, tj) = |branches(ti) ∩ branches(tj)| / |branches(ti) ∪ branches(tj)|
        """
        bi, bj = ti.branches_covered, tj.branches_covered
        union  = len(bi | bj)
        if union == 0:
            return 0.0
        return len(bi & bj) / union

    def _greedy_selection(
        self, sorted_trajectories: List[Trajectory]
    ) -> Tuple[List[Trajectory], Set]:
        """
        Greedy coverage-based selection with similarity fusion.

        Invariant: reduced_set is never empty when input is non-empty —
        we always keep at least the highest-priority trajectory.
        """
        reduced_set      = []
        covered_branches = set()
        remaining        = list(sorted_trajectories)
        iteration        = 0

        while remaining:
            iteration += 1

            # Always take the head (highest remaining priority)
            best      = remaining[0]
            remaining = remaining[1:]

            new_branches = best.branches_covered - covered_branches

            if len(new_branches) == 0 and len(reduced_set) > 0:
                # This trajectory adds no new coverage → fuse / discard
                # (keep on first iteration so we always select ≥ 1)
                continue

            # ── Add to reduced set ────────────────────────────────────
            reduced_set.append(best)
            covered_branches.update(best.branches_covered)

            print(f"   Iteration {iteration}: Selected {best.path_id}")
            print(f"      New branches: {len(new_branches)}, "
                  f"Total covered: {len(covered_branches)}")

            # ── Remove similar trajectories (fusion step) ─────────────
            to_remove = [t for t in remaining
                         if self._calculate_similarity(best, t) > self.theta]

            if to_remove:
                print(f"      Fused {len(to_remove)} similar trajectories "
                      f"(sim > {self.theta})")
                for t in to_remove:
                    remaining.remove(t)

        return reduced_set, covered_branches

    # ──────────────────────────────────────────────────────────────────────
    # Utilities
    # ──────────────────────────────────────────────────────────────────────

    def _detect_branches_mode(self, trajectories: List[Trajectory]) -> str:
        """
        Returns:
          'normal'  — branches_covered populated for all trajectories
          'partial' — some trajectories have branches, some don't
          'empty'   — branches_covered is empty for every trajectory
                      (deserialization problem upstream)
        """
        populated = sum(1 for t in trajectories if t.branches_covered)
        if populated == len(trajectories):
            return "normal"
        if populated == 0:
            return "empty"
        return "partial"

    def _get_all_branches(self, trajectories: List[Trajectory]) -> Set:
        """Union of all branches across the trajectory set."""
        result = set()
        for t in trajectories:
            result.update(t.branches_covered)
        return result