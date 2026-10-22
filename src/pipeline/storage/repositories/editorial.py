"""Repositories for the durable editorial hierarchy and composition references."""

from __future__ import annotations

from pipeline.contracts.editorial import (
    CompositionRef,
    ContentPackage,
    Cut,
    Episode,
    LayerInstance,
    Scene,
    Sequence,
    Shot,
)
from pipeline.storage.repositories.base import SqliteRepository


class ContentPackageRepository(SqliteRepository[ContentPackage]):
    model = ContentPackage
    table = "content_packages"
    key_columns = ("content_package_id",)
    columns = ("content_package_id", "production_idea_id", "active_episode_id")
    order_by = ("content_package_id",)


class EpisodeRepository(SqliteRepository[Episode]):
    model = Episode
    table = "episodes"
    key_columns = ("episode_id",)
    columns = (
        "episode_id",
        "content_package_id",
        "script_artifact_id",
        "version",
    )
    order_by = ("content_package_id", "version", "episode_id")

    def list_for_package(self, content_package_id: str) -> list[Episode]:
        rows = self.connection.execute(
            "SELECT payload FROM episodes WHERE content_package_id = ? "
            "ORDER BY version, episode_id",
            (content_package_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class CutRepository(SqliteRepository[Cut]):
    model = Cut
    table = "cuts"
    key_columns = ("cut_id",)
    columns = (
        "cut_id",
        "episode_id",
        "kind",
        "output_profile_id",
        "selection_manifest_id",
    )
    order_by = ("episode_id", "cut_id")

    def list_for_episode(self, episode_id: str) -> list[Cut]:
        rows = self.connection.execute(
            "SELECT payload FROM cuts WHERE episode_id = ? ORDER BY cut_id",
            (episode_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class SequenceRepository(SqliteRepository[Sequence]):
    model = Sequence
    table = "sequences"
    key_columns = ("sequence_id",)
    columns = ("sequence_id", "episode_id", "order_index")
    order_by = ("episode_id", "order_index", "sequence_id")

    def list_for_episode(self, episode_id: str) -> list[Sequence]:
        rows = self.connection.execute(
            "SELECT payload FROM sequences WHERE episode_id = ? "
            "ORDER BY order_index, sequence_id",
            (episode_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class SceneRepository(SqliteRepository[Scene]):
    model = Scene
    table = "scenes"
    key_columns = ("scene_id",)
    columns = (
        "scene_id",
        "sequence_id",
        "order_index",
        "narration_artifact_id",
    )
    order_by = ("sequence_id", "order_index", "scene_id")

    def list_for_sequence(self, sequence_id: str) -> list[Scene]:
        rows = self.connection.execute(
            "SELECT payload FROM scenes WHERE sequence_id = ? "
            "ORDER BY order_index, scene_id",
            (sequence_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class ShotRepository(SqliteRepository[Shot]):
    model = Shot
    table = "shots"
    key_columns = ("shot_id",)
    columns = (
        "shot_id",
        "scene_id",
        "order_index",
        "start_frame",
        "end_frame",
    )
    order_by = ("scene_id", "order_index", "shot_id")

    def list_for_scene(self, scene_id: str) -> list[Shot]:
        rows = self.connection.execute(
            "SELECT payload FROM shots WHERE scene_id = ? "
            "ORDER BY order_index, shot_id",
            (scene_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class LayerInstanceRepository(SqliteRepository[LayerInstance]):
    model = LayerInstance
    table = "layer_instances"
    key_columns = ("layer_id",)
    columns = (
        "layer_id",
        "shot_id",
        "kind",
        "start_frame",
        "end_frame",
        "asset_instance_id",
        "payload_artifact_id",
        "z_index",
    )
    order_by = ("shot_id", "z_index", "start_frame", "layer_id")

    def list_for_shot(self, shot_id: str) -> list[LayerInstance]:
        rows = self.connection.execute(
            "SELECT payload FROM layer_instances WHERE shot_id = ? "
            "ORDER BY z_index, start_frame, layer_id",
            (shot_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class CompositionRefRepository(SqliteRepository[CompositionRef]):
    model = CompositionRef
    table = "composition_refs"
    key_columns = ("composition_artifact_id",)
    columns = (
        "composition_artifact_id",
        "cut_id",
        "render_profile_id",
        "render_profile_hash",
        "timebase",
    )
    order_by = ("cut_id", "render_profile_id", "composition_artifact_id")

    def list_for_cut(self, cut_id: str) -> list[CompositionRef]:
        rows = self.connection.execute(
            "SELECT payload FROM composition_refs WHERE cut_id = ? "
            "ORDER BY render_profile_id, composition_artifact_id",
            (cut_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


__all__ = [
    "CompositionRefRepository",
    "ContentPackageRepository",
    "CutRepository",
    "EpisodeRepository",
    "LayerInstanceRepository",
    "SceneRepository",
    "SequenceRepository",
    "ShotRepository",
]
