"""Repositories for immutable artifacts, lineage, and selection pointers."""

from __future__ import annotations

from pipeline.contracts.artifacts import Artifact, ArtifactDependency, ArtifactPointer
from pipeline.contracts.vocabularies import ArtifactPointerType
from pipeline.storage.repositories.base import SqliteRepository


class ArtifactRepository(SqliteRepository[Artifact]):
    model = Artifact
    table = "artifacts"
    key_columns = ("artifact_id",)
    columns = (
        "artifact_id",
        "run_id",
        "logical_slot",
        "artifact_type",
        "version",
        "uri",
        "sha256",
        "size_bytes",
        "media_type",
        "producer_attempt_id",
        "producer_version",
        "config_hash",
        "state",
        "retention_class",
        "created_at",
    )
    order_by = ("run_id", "logical_slot", "version", "artifact_id")

    def list_for_run(self, run_id: str) -> list[Artifact]:
        rows = self.connection.execute(
            "SELECT payload FROM artifacts WHERE run_id = ? "
            "ORDER BY logical_slot, version, artifact_id",
            (run_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def get_by_slot_version(
        self, run_id: str, logical_slot: str, version: int
    ) -> Artifact | None:
        row = self.connection.execute(
            "SELECT payload FROM artifacts "
            "WHERE run_id = ? AND logical_slot = ? AND version = ?",
            (run_id, logical_slot, version),
        ).fetchone()
        if row is None:
            return None
        return self.model.model_validate_json(row[0])

    def next_version(self, run_id: str, logical_slot: str) -> int:
        """Return the next free replacement revision for a logical slot."""

        row = self.connection.execute(
            "SELECT MAX(version) FROM artifacts WHERE run_id = ? AND logical_slot = ?",
            (run_id, logical_slot),
        ).fetchone()
        current = int(row[0]) if row is not None and row[0] is not None else 0
        return current + 1

    def list_by_sha256(self, sha256: str) -> list[Artifact]:
        rows = self.connection.execute(
            "SELECT payload FROM artifacts WHERE sha256 = ? "
            "ORDER BY created_at, artifact_id",
            (sha256,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class ArtifactDependencyRepository(SqliteRepository[ArtifactDependency]):
    model = ArtifactDependency
    table = "artifact_dependencies"
    key_columns = ("parent_artifact_id", "child_artifact_id")
    columns = (
        "parent_artifact_id",
        "child_artifact_id",
        "dependency_type",
    )
    order_by = ("parent_artifact_id", "child_artifact_id")

    def list_for_parent(self, parent_artifact_id: str) -> list[ArtifactDependency]:
        rows = self.connection.execute(
            "SELECT payload FROM artifact_dependencies "
            "WHERE parent_artifact_id = ? ORDER BY child_artifact_id",
            (parent_artifact_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def list_for_child(self, child_artifact_id: str) -> list[ArtifactDependency]:
        rows = self.connection.execute(
            "SELECT payload FROM artifact_dependencies "
            "WHERE child_artifact_id = ? ORDER BY parent_artifact_id",
            (child_artifact_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class ArtifactPointerRepository(SqliteRepository[ArtifactPointer]):
    model = ArtifactPointer
    table = "artifact_pointers"
    key_columns = ("pointer_id",)
    columns = (
        "pointer_id",
        "run_id",
        "logical_slot",
        "artifact_id",
        "pointer_type",
        "active",
        "updated_at",
    )
    order_by = ("run_id", "logical_slot", "pointer_type", "pointer_id")

    def list_for_slot(
        self,
        run_id: str,
        logical_slot: str,
        *,
        pointer_type: ArtifactPointerType | None = None,
    ) -> list[ArtifactPointer]:
        if pointer_type is None:
            rows = self.connection.execute(
                "SELECT payload FROM artifact_pointers "
                "WHERE run_id = ? AND logical_slot = ? "
                "ORDER BY pointer_type, pointer_id",
                (run_id, logical_slot),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT payload FROM artifact_pointers "
                "WHERE run_id = ? AND logical_slot = ? AND pointer_type = ? "
                "ORDER BY pointer_id",
                (run_id, logical_slot, pointer_type.value),
            ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def get_active(
        self,
        run_id: str,
        logical_slot: str,
        pointer_type: ArtifactPointerType,
    ) -> ArtifactPointer | None:
        row = self.connection.execute(
            "SELECT payload FROM artifact_pointers "
            "WHERE run_id = ? AND logical_slot = ? AND pointer_type = ? AND active = 1",
            (run_id, logical_slot, pointer_type.value),
        ).fetchone()
        if row is None:
            return None
        return self.model.model_validate_json(row[0])

    def list_active_for_run(self, run_id: str) -> list[ArtifactPointer]:
        rows = self.connection.execute(
            "SELECT payload FROM artifact_pointers WHERE run_id = ? AND active = 1 "
            "ORDER BY logical_slot, pointer_type, pointer_id",
            (run_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def activate(self, pointer: ArtifactPointer) -> ArtifactPointer:
        """Insert a pointer after deactivating the prior active term.

        The partial unique index allows only one active pointer per
        ``(run_id, logical_slot, pointer_type)``. The caller must run this
        method inside a transaction so the deactivation and insertion commit
        atomically.
        """

        if not pointer.active:
            raise ValueError("activate() requires a pointer with active=True")
        active_pointer = self.get_active(
            pointer.run_id, pointer.logical_slot, pointer.pointer_type
        )
        if active_pointer is not None:
            if active_pointer.pointer_id == pointer.pointer_id:
                raise ValueError(
                    "activate() requires a new pointer record, not the active one"
                )
            deactivated = active_pointer.model_copy(
                update={"active": False, "updated_at": pointer.updated_at}
            )
            self.update(deactivated)
        return self.insert(pointer)


__all__ = [
    "ArtifactDependencyRepository",
    "ArtifactPointerRepository",
    "ArtifactRepository",
]
