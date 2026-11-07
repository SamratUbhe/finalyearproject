"""Persistent review history storage and scan comparison engine."""

import json
import logging
import os
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Set, Union
import uuid

from src.core.models import (
    ConsolidatedReview,
    ModeratedFinding,
    SeverityEnum,
)

logger = logging.getLogger("reviewer.storage.history")


class ReviewHistoryStorage:
    """Manages serialization, indexed metadata, and differential comparison of review scans."""

    def __init__(self, storage_dir: Optional[Union[str, Path]] = None) -> None:
        """Initialize review history storage.

        Args:
            storage_dir: Optional custom storage directory. Defaults to `.gsd/reviews/` in workspace root.
        """
        if storage_dir is not None:
            self.storage_dir = Path(storage_dir).resolve()
        else:
            project_root = Path(__file__).resolve().parent.parent.parent
            self.storage_dir = (project_root / ".gsd" / "reviews").resolve()

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_index()

    @property
    def index_file(self) -> Path:
        """Path to metadata index JSON file."""
        return self.storage_dir / "index.json"

    def _ensure_index(self) -> None:
        """Ensure that index.json exists on disk."""
        if not self.index_file.exists():
            with self._lock:
                if not self.index_file.exists():
                    self.index_file.write_text("[]", encoding="utf-8")

    def _read_index(self) -> List[Dict[str, Any]]:
        """Read and parse the current metadata index."""
        if not self.index_file.exists():
            return []
        try:
            raw = self.index_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            return []
        except Exception as exc:
            logger.warning("Failed to parse history index: %s", exc)
            return []

    def _write_index(self, index_data: List[Dict[str, Any]]) -> None:
        """Atomically write updated metadata index."""
        temp_file = self.storage_dir / f"index_{uuid.uuid4().hex}.tmp"
        temp_file.write_text(json.dumps(index_data, indent=2), encoding="utf-8")
        temp_file.replace(self.index_file)

    def save_review(self, review: ConsolidatedReview) -> Path:
        """Serialize complete ConsolidatedReview and update index metadata.

        Args:
            review: ConsolidatedReview instance to save.

        Returns:
            Path to the saved review JSON file.
        """
        file_path = self.storage_dir / f"{review.review_id}.json"
        temp_file = self.storage_dir / f"{review.review_id}_{uuid.uuid4().hex}.tmp"
        temp_file.write_text(review.model_dump_json(indent=2), encoding="utf-8")
        temp_file.replace(file_path)

        # Compute max risk score safely
        raw_max = review.risk_summary.get("max_risk_score")
        if raw_max is None:
            max_risk = max((f.risk_score for f in review.findings), default=0.0)
        else:
            try:
                max_risk = float(raw_max)
            except (ValueError, TypeError):
                max_risk = 0.0

        metadata: Dict[str, Any] = {
            "review_id": review.review_id,
            "repo_id": review.repo_id,
            "created_at": review.created_at,
            "status": review.status,
            "total_files": review.total_files_reviewed,
            "total_chunks": review.total_chunks_reviewed,
            "total_findings": len(review.findings),
            "severity_distribution": dict(review.severity_distribution),
            "max_risk_score": round(max_risk, 2),
        }

        with self._lock:
            index_data = self._read_index()
            updated = False
            for idx, item in enumerate(index_data):
                if item.get("review_id") == review.review_id:
                    index_data[idx] = metadata
                    updated = True
                    break
            if not updated:
                index_data.append(metadata)
            self._write_index(index_data)

        logger.info("Saved review %s for repo %s", review.review_id, review.repo_id)
        return file_path

    def list_reviews(
        self, repo_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List historical review runs from the lightweight metadata index.

        Args:
            repo_id: Optional repository identifier filter.
            limit: Maximum records to return.

        Returns:
            List of summary metadata dictionaries sorted descending by created_at.
        """
        if hasattr(limit, "default"):
            limit = getattr(limit, "default")
        try:
            limit_val = int(limit) if limit is not None else 50
        except (ValueError, TypeError):
            limit_val = 50

        with self._lock:
            index_data = self._read_index()

        if repo_id:
            index_data = [item for item in index_data if item.get("repo_id") == repo_id]

        index_data.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return index_data[:limit_val]

    def get_review(self, review_id: str) -> Optional[ConsolidatedReview]:
        """Load and deserialize a ConsolidatedReview by ID.

        Args:
            review_id: UUID of the review.

        Returns:
            ConsolidatedReview instance or None if not found or corrupted.
        """
        file_path = self.storage_dir / f"{review_id}.json"
        if not file_path.is_file():
            return None

        try:
            content = file_path.read_text(encoding="utf-8")
            return ConsolidatedReview.model_validate_json(content)
        except Exception as exc:
            logger.error("Failed to parse review file %s: %s", file_path, exc)
            return None

    def delete_review(self, review_id: str) -> bool:
        """Delete stored review JSON and update metadata index.

        Args:
            review_id: UUID of the review to delete.

        Returns:
            True if review existed and was removed, False otherwise.
        """
        file_path = self.storage_dir / f"{review_id}.json"
        file_existed = False
        if file_path.is_file():
            try:
                file_path.unlink()
                file_existed = True
            except Exception as exc:
                logger.warning("Could not unlink review file %s: %s", file_path, exc)

        with self._lock:
            index_data = self._read_index()
            initial_count = len(index_data)
            index_data = [item for item in index_data if item.get("review_id") != review_id]
            index_modified = len(index_data) < initial_count
            if index_modified:
                self._write_index(index_data)

        return file_existed or index_modified

    def compare_reviews(
        self, base_review_id: str, target_review_id: str
    ) -> Dict[str, Any]:
        """Compare findings between a base and target review to determine delta.

        Args:
            base_review_id: Earlier or baseline review ID.
            target_review_id: Subsequent or comparison review ID.

        Returns:
            Structured comparison dictionary with new, resolved, and persistent findings.

        Raises:
            ValueError: If either review ID is not found.
        """
        base_review = self.get_review(base_review_id)
        if base_review is None:
            raise ValueError(f"Base review '{base_review_id}' not found")

        target_review = self.get_review(target_review_id)
        if target_review is None:
            raise ValueError(f"Target review '{target_review_id}' not found")

        def _normalize_path(p: str) -> str:
            return Path(p).as_posix().lower()

        def _findings_match(f1: ModeratedFinding, f2: ModeratedFinding) -> bool:
            # 1. Evidence file path match
            if _normalize_path(f1.finding.evidence.file_path) != _normalize_path(
                f2.finding.evidence.file_path
            ):
                return False

            # 2. Line spans overlap or within 5-line distance
            overlap = max(
                f1.finding.evidence.start_line, f2.finding.evidence.start_line
            ) <= min(f1.finding.evidence.end_line, f2.finding.evidence.end_line)
            line_distance = (
                abs(f1.finding.evidence.start_line - f2.finding.evidence.start_line) <= 5
            )
            if not (overlap or line_distance):
                return False

            # 3. CWE match OR Jaccard similarity > 0.3
            cwe1 = f1.finding.cwe_id.strip() if f1.finding.cwe_id else None
            cwe2 = f2.finding.cwe_id.strip() if f2.finding.cwe_id else None
            if cwe1 and cwe2 and cwe1.lower() == cwe2.lower():
                return True

            tokens1 = set(f1.finding.title.lower().split())
            tokens2 = set(f2.finding.title.lower().split())
            if not tokens1 and not tokens2:
                return True
            union = tokens1 | tokens2
            if not union:
                return False
            jaccard = len(tokens1 & tokens2) / len(union)
            return jaccard > 0.3

        base_matched_indices: Set[int] = set()
        target_matched_indices: Set[int] = set()
        persistent_findings: List[ModeratedFinding] = []

        for t_idx, t_finding in enumerate(target_review.findings):
            for b_idx, b_finding in enumerate(base_review.findings):
                if b_idx in base_matched_indices:
                    continue
                if _findings_match(b_finding, t_finding):
                    base_matched_indices.add(b_idx)
                    target_matched_indices.add(t_idx)
                    persistent_findings.append(t_finding)
                    break

        new_findings: List[ModeratedFinding] = [
            f
            for idx, f in enumerate(target_review.findings)
            if idx not in target_matched_indices
        ]
        resolved_findings: List[ModeratedFinding] = [
            f
            for idx, f in enumerate(base_review.findings)
            if idx not in base_matched_indices
        ]

        # Max risk score delta calculation
        base_max = base_review.risk_summary.get("max_risk_score")
        if base_max is None:
            base_max_risk = max((f.risk_score for f in base_review.findings), default=0.0)
        else:
            try:
                base_max_risk = float(base_max)
            except (ValueError, TypeError):
                base_max_risk = 0.0

        target_max = target_review.risk_summary.get("max_risk_score")
        if target_max is None:
            target_max_risk = max((f.risk_score for f in target_review.findings), default=0.0)
        else:
            try:
                target_max_risk = float(target_max)
            except (ValueError, TypeError):
                target_max_risk = 0.0

        risk_score_delta = round(target_max_risk - base_max_risk, 2)

        # Critical counts delta calculation
        base_critical = base_review.severity_distribution.get("CRITICAL")
        if base_critical is None:
            base_critical = sum(
                1 for f in base_review.findings if f.finding.severity == SeverityEnum.CRITICAL
            )

        target_critical = target_review.severity_distribution.get("CRITICAL")
        if target_critical is None:
            target_critical = sum(
                1 for f in target_review.findings if f.finding.severity == SeverityEnum.CRITICAL
            )

        critical_delta = target_critical - base_critical

        summary: Dict[str, Any] = {
            "base_review_id": base_review_id,
            "target_review_id": target_review_id,
            "base_total": len(base_review.findings),
            "target_total": len(target_review.findings),
            "new_count": len(new_findings),
            "resolved_count": len(resolved_findings),
            "persistent_count": len(persistent_findings),
            "risk_score_delta": risk_score_delta,
            "critical_delta": critical_delta,
        }

        return {
            "base_review_id": base_review_id,
            "target_review_id": target_review_id,
            "base_total": len(base_review.findings),
            "target_total": len(target_review.findings),
            "new_count": len(new_findings),
            "resolved_count": len(resolved_findings),
            "persistent_count": len(persistent_findings),
            "risk_score_delta": risk_score_delta,
            "critical_delta": critical_delta,
            "new_findings": new_findings,
            "resolved_findings": resolved_findings,
            "persistent_findings": persistent_findings,
            "summary": summary,
        }
