from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pipeline.contracts.artifacts import Artifact, ArtifactDependency, ArtifactPointer
from pipeline.contracts.capabilities import BudgetReservation, IdempotencyRecord
from pipeline.contracts.config import EffectiveConfig
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
from pipeline.contracts.execution import StageAttempt, StageInstance, WorkflowRun
from pipeline.contracts.jobs import Job, Lease
from pipeline.contracts.vocabularies import (
    AcceptanceStatus,
    ArtifactPointerType,
    ArtifactState,
    AttemptStatus,
    BudgetReservationStatus,
    BudgetScopeType,
    EditorialCutKind,
    IdempotencyStatus,
    JobStatus,
    LayerKind,
    RunStatus,
    StageExecutionStatus,
)
from pipeline.fingerprints import sha256_bytes, sha256_text
from pipeline.storage import ArtifactStore, Database, MigrationRunner

BASE_TIME = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
HASH_A = sha256_text("fixture-a")
HASH_B = sha256_text("fixture-b")


def at(minutes: int = 0) -> datetime:
    return BASE_TIME + timedelta(minutes=minutes)


class RecordFactory:
    """Build deterministic, internally consistent durable records."""

    def effective_config(
        self, suffix: str = "01", *, config_hash: str = HASH_A
    ) -> EffectiveConfig:
        return EffectiveConfig(
            schema_version="effective-config.v1",
            effective_config_id=f"cfg_{suffix}",
            system_policy_version="1.0",
            domain_profile_id="software_engineering_explainer_v1",
            domain_profile_version="1.0",
            channel_profile_id="channel_explainer_v1",
            channel_profile_version="1.0",
            workflow_id="explainer_validation_v1",
            workflow_version="1.0",
            run_overrides={
                "schema_version": "run-overrides.v1",
                "locale": "en-US",
            },
            resolved_values={"locale": "en-US"},
            source_map={"locale": "channel_profile:channel_explainer_v1"},
            config_hash=config_hash,
            snapshot_artifact_id=None,
        )

    def run(
        self,
        config: EffectiveConfig,
        suffix: str = "01",
        *,
        run_key: str | None = None,
        status: RunStatus = RunStatus.RUNNING,
    ) -> WorkflowRun:
        return WorkflowRun(
            schema_version="workflow-run.v1",
            run_id=f"run_{suffix}",
            run_key=run_key or f"run-key:{suffix}",
            workflow_id=config.workflow_id,
            workflow_version=config.workflow_version,
            effective_config_id=config.effective_config_id,
            effective_config_hash=config.config_hash,
            status=status,
            content_package_id=f"package_{suffix}",
            created_at=at(0),
            updated_at=at(10),
        )

    def stage_instance(
        self,
        run: WorkflowRun,
        suffix: str = "01",
        *,
        node_id: str = "script",
        logical_item_key: str = "episode",
        execution_status: StageExecutionStatus = StageExecutionStatus.SUCCEEDED,
        acceptance_status: AcceptanceStatus = AcceptanceStatus.PASSED,
    ) -> StageInstance:
        return StageInstance(
            schema_version="stage-instance.v1",
            stage_instance_id=f"stage_{suffix}",
            run_id=run.run_id,
            node_id=node_id,
            logical_item_key=logical_item_key,
            execution_status=execution_status,
            acceptance_status=acceptance_status,
            quality_gate_id="script_gate_v1",
            expected_input_manifest_id=None,
            active_attempt_id=f"attempt_{suffix}",
            accepted_output_artifact_ids=[],
            created_at=at(1),
            updated_at=at(20),
        )

    def stage_attempt(
        self,
        stage: StageInstance,
        suffix: str = "01",
        *,
        attempt_number: int = 1,
        status: AttemptStatus = AttemptStatus.SUCCEEDED,
    ) -> StageAttempt:
        return StageAttempt(
            schema_version="stage-attempt.v1",
            attempt_id=f"attempt_{suffix}",
            stage_instance_id=stage.stage_instance_id,
            attempt_number=attempt_number,
            quality_regeneration_number=0,
            status=status,
            input_artifact_ids=[],
            output_artifact_ids=[],
            worker_id="worker_local_01",
            lease_expires_at=at(30),
            started_at=at(5),
            finished_at=at(10) if status is AttemptStatus.SUCCEEDED else None,
        )

    def job(
        self,
        attempt: StageAttempt,
        suffix: str = "01",
        *,
        idempotency_key: str | None = None,
        status: JobStatus = JobStatus.READY,
    ) -> Job:
        return Job(
            schema_version="job.v1",
            job_id=f"job_{suffix}",
            attempt_id=attempt.attempt_id,
            queue_name="capability_default",
            status=status,
            idempotency_key=idempotency_key or f"idem_job_{suffix}",
            available_at=at(10),
            delivery_count=0,
        )

    def lease(self, job: Job, *, fencing_token: int = 1) -> Lease:
        return Lease(
            schema_version="lease.v1",
            job_id=job.job_id,
            owner_id="worker_local_01",
            fencing_token=fencing_token,
            acquired_at=at(20),
            expires_at=at(25),
            heartbeat_at=at(21),
        )

    def idempotency_record(
        self,
        suffix: str = "01",
        *,
        key: str | None = None,
        status: IdempotencyStatus = IdempotencyStatus.SUCCEEDED,
    ) -> IdempotencyRecord:
        return IdempotencyRecord(
            schema_version="idempotency-record.v1",
            idempotency_key=key or f"idem_capability_{suffix}",
            capability="speech_generation",
            operation_version="v1",
            request_fingerprint=HASH_B,
            input_artifact_ids=[],
            required_features=[],
            locale=None,
            provider="local_speech_fixture",
            status=status,
            capability_execution_id=f"capexec_{suffix}",
            result_artifact_ids=[],
            created_at=at(20),
            completed_at=at(25) if status is IdempotencyStatus.SUCCEEDED else None,
        )

    def budget_reservation(
        self,
        suffix: str = "01",
        *,
        idempotency_key: str | None = None,
        scope_type: BudgetScopeType = BudgetScopeType.RUN,
        scope_id: str = "run_01",
    ) -> BudgetReservation:
        return BudgetReservation(
            schema_version="budget-reservation.v1",
            reservation_id=f"reservation_{suffix}",
            scope_type=scope_type,
            scope_id=scope_id,
            idempotency_key=idempotency_key or f"idem_budget_{suffix}",
            estimated_cost_minor=3,
            reserved_cost_minor=5,
            actual_cost_minor=2,
            status=BudgetReservationStatus.SETTLED,
            created_at=at(20),
            settled_at=at(30),
        )

    def artifact(
        self,
        run: WorkflowRun,
        attempt: StageAttempt,
        suffix: str = "01",
        *,
        logical_slot: str | None = None,
        version: int = 1,
        content: bytes | None = None,
        state: ArtifactState = ArtifactState.ACCEPTED,
    ) -> Artifact:
        slot = logical_slot or f"slot_{suffix}"
        payload_bytes = (
            content if content is not None else f"artifact-bytes-{suffix}".encode()
        )
        digest = sha256_bytes(payload_bytes)
        return Artifact(
            schema_version="artifact.v1",
            artifact_id=f"artifact_{suffix}",
            run_id=run.run_id,
            logical_slot=slot,
            artifact_type="script",
            version=version,
            uri=f"artifact://sha256/{digest}",
            sha256=digest,
            size_bytes=len(payload_bytes),
            media_type="text/markdown",
            media_metadata={},
            producer_attempt_id=attempt.attempt_id,
            producer_version="fixture.v1",
            input_artifact_ids=[],
            config_hash=run.effective_config_hash,
            state=state,
            retention_class="intermediate",
            created_at=at(30),
        )

    def dependency(
        self,
        parent: Artifact,
        child: Artifact,
        *,
        dependency_type: str = "input",
    ) -> ArtifactDependency:
        return ArtifactDependency(
            schema_version="artifact-dependency.v1",
            parent_artifact_id=parent.artifact_id,
            child_artifact_id=child.artifact_id,
            dependency_type=dependency_type,
        )

    def pointer(
        self,
        run: WorkflowRun,
        artifact: Artifact,
        suffix: str = "01",
        *,
        pointer_type: ArtifactPointerType = ArtifactPointerType.CURRENT,
        active: bool = True,
    ) -> ArtifactPointer:
        return ArtifactPointer(
            schema_version="artifact-pointer.v1",
            pointer_id=f"pointer_{suffix}",
            run_id=run.run_id,
            logical_slot=artifact.logical_slot,
            artifact_id=artifact.artifact_id,
            pointer_type=pointer_type,
            active=active,
            updated_at=at(35),
        )

    def content_package(self, suffix: str = "01") -> ContentPackage:
        return ContentPackage(
            schema_version="content-package.v1",
            content_package_id=f"package_{suffix}",
            production_idea_id=f"idea_{suffix}",
            episode_ids=[f"episode_{suffix}"],
            active_episode_id=f"episode_{suffix}",
        )

    def episode(self, package: ContentPackage, suffix: str = "01") -> Episode:
        return Episode(
            schema_version="episode.v1",
            episode_id=f"episode_{suffix}",
            content_package_id=package.content_package_id,
            script_artifact_id=f"artifact_script_{suffix}",
            sequence_ids=[f"sequence_{suffix}"],
            cut_ids=[f"cut_{suffix}"],
            version=1,
        )

    def cut(self, episode: Episode, suffix: str = "01") -> Cut:
        return Cut(
            schema_version="cut.v1",
            cut_id=f"cut_{suffix}",
            episode_id=episode.episode_id,
            kind=EditorialCutKind.LONG_FORM,
            output_profile_id="landscape_1080p_30_v1",
            sequence_ids=list(episode.sequence_ids),
            selection_manifest_id=None,
        )

    def sequence(self, episode: Episode, suffix: str = "01") -> Sequence:
        return Sequence(
            schema_version="sequence.v1",
            sequence_id=f"sequence_{suffix}",
            episode_id=episode.episode_id,
            order_index=0,
            scene_ids=[f"scene_{suffix}"],
        )

    def scene(self, sequence: Sequence, suffix: str = "01") -> Scene:
        return Scene(
            schema_version="scene.v1",
            scene_id=f"scene_{suffix}",
            sequence_id=sequence.sequence_id,
            order_index=0,
            narration_artifact_id=f"artifact_narration_{suffix}",
            claim_ids=[],
            shot_ids=[f"shot_{suffix}"],
        )

    def shot(self, scene: Scene, suffix: str = "01") -> Shot:
        return Shot(
            schema_version="shot.v1",
            shot_id=f"shot_{suffix}",
            scene_id=scene.scene_id,
            order_index=0,
            start_frame=0,
            end_frame=90,
            layer_ids=[f"layer_{suffix}"],
        )

    def layer(self, shot: Shot, suffix: str = "01") -> LayerInstance:
        return LayerInstance(
            schema_version="layer-instance.v1",
            layer_id=f"layer_{suffix}",
            shot_id=shot.shot_id,
            kind=LayerKind.IMAGE,
            start_frame=0,
            end_frame=90,
            asset_instance_id=f"asset_{suffix}",
            payload_artifact_id=None,
            z_index=0,
            properties={"fit": "cover"},
        )

    def composition_ref(self, cut: Cut, suffix: str = "01") -> CompositionRef:
        return CompositionRef(
            schema_version="composition-ref.v1",
            composition_artifact_id=f"composition_{suffix}",
            cut_id=cut.cut_id,
            render_profile_id=cut.output_profile_id,
            render_profile_hash=HASH_A,
            timebase="1/30",
        )

    def graph(self) -> list[tuple[str, object]]:
        """Return one valid record per typed repository in insert order."""

        config = self.effective_config()
        run = self.run(config)
        stage = self.stage_instance(run)
        attempt = self.stage_attempt(stage)
        job = self.job(attempt)
        lease = self.lease(job)
        parent = self.artifact(run, attempt, "parent", logical_slot="script")
        child = self.artifact(run, attempt, "child", logical_slot="speech")
        dependency = self.dependency(parent, child)
        pointer = self.pointer(run, parent)
        package = self.content_package()
        episode = self.episode(package)
        cut = self.cut(episode)
        sequence = self.sequence(episode)
        scene = self.scene(sequence)
        shot = self.shot(scene)
        layer = self.layer(shot)
        composition = self.composition_ref(cut)
        return [
            ("effective_config", config),
            ("run", run),
            ("stage_instance", stage),
            ("stage_attempt", attempt),
            ("job", job),
            ("lease", lease),
            ("idempotency_record", self.idempotency_record()),
            ("budget_reservation", self.budget_reservation()),
            ("artifact_parent", parent),
            ("artifact_child", child),
            ("artifact_dependency", dependency),
            ("artifact_pointer", pointer),
            ("content_package", package),
            ("episode", episode),
            ("cut", cut),
            ("sequence", sequence),
            ("scene", scene),
            ("shot", shot),
            ("layer_instance", layer),
            ("composition_ref", composition),
        ]


@pytest.fixture
def database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "state" / "pipeline.sqlite3")
    MigrationRunner(database).migrate()
    return database


@pytest.fixture
def records() -> RecordFactory:
    return RecordFactory()


@pytest.fixture
def artifact_store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(pipeline_home=tmp_path / "pipeline-home")
