# AI Video Automation Pipeline — Content Model and Composition

**Status:** Canonical media design

**Purpose:** Define the editorial and temporal units used to build landscape long-form episodes and derived vertical shorts.

## 1. Design goals

The content model must support:

- ten-minute-plus landscape explainers;
- scene-level narration and repair;
- multiple shots per scene;
- procedural graphics and code-generated visuals;
- stock, public-domain, and generated media;
- captions, charts, diagrams, code, overlays, and transitions;
- audio timing and word-level alignment;
- landscape and vertical cuts from the same episode;
- deterministic reconstruction from immutable inputs;
- technical and semantic QC at the right granularity.

It must not create a workflow record for every rendered frame or pixel.

## 2. Content hierarchy

```text
ContentPackage
└── Episode
    ├── Editorial Sequence[]
    │   └── Scene[]
    │       └── Shot[]
    │           └── LayerInstance[]
    │               └── AssetInstance
    │                   └── SourceAsset → Artifact
    └── Cut[]
        └── CutSelection / composition / render artifacts
```

### 2.1 Episode

The editorial work and shared source material. It is not an encoded file. An episode has:

- episode ID and version;
- production idea;
- domain/channel profile;
- approved script/version;
- claim ledger and evidence references;
- visual plan;
- audio plan;
- cut manifests;
- artifact graph and publication history.

### 2.2 Cut

A deliverable variant with its own:

- cut ID and output profile;
- selected sequences/scenes/shots;
- composition specification;
- captions/metadata;
- render artifacts;
- QC results;
- publication status.

`Sequence`, `Scene`, and `Shot` are episode-level editorial objects. A `Cut`
selects and orders those objects through an explicit cut-selection manifest; it
does not imply that a short owns a second, silently copied scene tree. A short
may create new cut-specific composition scenes/shots when vertical
recomposition changes timing or framing, but each derived object retains its
source episode IDs and repair lineage.

Examples:

```text
episode_001 / cut_long_form_16x9
episode_001 / cut_short_01_9x16
episode_001 / cut_short_02_9x16
```

### 2.3 Sequence

A chapter/section with a stable semantic identity. Sequences are useful for long-form navigation, chapter metadata, and grouped visual treatment.

### 2.4 Scene

A narration-centered semantic unit. A scene contains:

- scene ID;
- sequence ID;
- narration text;
- claim IDs;
- visual intent;
- duration policy;
- caption text;
- pronunciation hints;
- expected audio/timing artifacts;
- one or more shots.

Scenes are the initial preferred semantic repair boundary.

### 2.5 Shot

A temporal visual treatment within a scene. A shot has:

- shot ID;
- start/end time or frame;
- visual purpose;
- asset instances;
- camera/crop/transform;
- transition policy;
- layers;
- optional text/graphic data.

A scene can contain a single static shot or many shots that change as narration progresses.

### 2.6 Layer instance

A placed timeline element. Initial layer kinds:

```text
video
image
shape
chart
code
text
caption
audio_voice
audio_music
audio_effect
mask
transition
```

Layer instances refer to source artifacts and hold placement-specific properties. They do not duplicate source bytes.

### 2.7 Source asset and asset instance

`SourceAsset` is the immutable obtained/generated media. `AssetInstance` is one
placement-specific use in a particular shot. `LayerInstance` owns timeline
layer behavior such as z-order, opacity, effects, and masks; it references an
`AssetInstance` when it displays media. The asset instance is authoritative for
source selection, crop, transform, and placement range. Do not duplicate those
fields with different meanings in a layer.

```text
SourceAsset:
  asset_id: asset_stock_abc
  sha256: ...
  provenance: ...

AssetInstance:
  instance_id: inst_scene_03_shot_02
  asset_id: asset_stock_abc
  crop: ...
  start_frame: 1200
  end_frame: 1500
  transform: ...
```

This allows one asset to be reused with different crops, durations, masks, and motion.

## 3. Frames, time, and granularity

Frames are a physical rendering unit. They are not normally a durable workflow
unit because per-frame records would overwhelm the graph and make repair
unnecessarily granular. Internal timeline ranges use half-open intervals
`[start_frame, end_frame)`; a range with equal endpoints is empty, and all
validators use the same convention.

Use:

- integer frame ranges for renderer timeline operations;
- explicit frame rate in the output profile;
- rational timebase where external media has non-integer timing;
- sample/frame artifacts for QC;
- word timestamps for speech/caption alignment;
- frame-level observations only when a defect is detected or sampled.

### Initial defaults

| Output | Dimensions | Frame rate | Audio |
|---|---:|---:|---|
| Landscape | 1920×1080 | 30 fps default | 48 kHz stereo default |
| Vertical | 1080×1920 | 30 fps default | 48 kHz stereo default |

These are profile defaults, not hidden constants. A renderer profile must declare codec/container, color space, pixel format, audio layout, loudness target, and caption policy.

## 4. Composition contract

The composition specification has two explicit schemas. Python stages produce a
nested `composition-authoring.v1` document; the renderer worker resolves it into
a self-contained `render-manifest.v1` (`CompositionSpec`) containing exact
ordered IDs, hashes, opaque URIs, timing, profile, and immutable artifact
references. TypeScript/Remotion consumes the resolved manifest, not mutable
database pointers.

Illustrative shape:

```json
{
  "schema_version": "composition-authoring.v1",
  "composition_id": "comp_001",
  "episode_id": "episode_001",
  "cut_id": "cut_long_form_16x9",
  "render_profile_id": "landscape_1080p_30_v1",
  "render_profile_hash": "sha256:...",
  "duration_frames": 18000,
  "sequences": [
    {
      "sequence_id": "seq_01",
      "scenes": [
        {
          "scene_id": "scene_01",
          "start_frame": 0,
          "end_frame": 900,
          "shots": [
            {
              "shot_id": "shot_01_01",
              "start_frame": 0,
              "end_frame": 900,
              "layers": [
                {
                  "layer_id": "layer_01",
                  "kind": "IMAGE",
                  "asset_instance_id": "asset_instance_01",
                  "start_frame": 0,
                  "end_frame": 900,
                  "transform": {"fit": "cover", "scale": 1.0},
                  "animation": {"type": "slow_zoom", "amount": 0.04}
                },
                {
                  "layer_id": "layer_caption_01",
                  "kind": "CAPTION",
                  "payload_artifact_id": "artifact_caption_scene_01",
                  "start_frame": 0,
                  "end_frame": 900,
                  "safe_area": "default"
                }
              ]
            }
          ]
        }
      ]
    }
  ],
  "audio_tracks": [
    {
      "track_id": "voice",
      "artifact_id": "artifact_voice_master",
      "start_frame": 0,
      "end_frame": 18000
    }
  ],
  "font_artifact_ids": ["font_brand_regular_v1"],
  "renderer_version": "remotion-profile-v1"
}
```

The real contract should be a typed `CompositionAuthoringSpec` plus generated/checked JSON Schema. The renderer must reject incompatible schemas before rendering. `render_profile_id` and `render_profile_hash` are part of composition identity; changing codec, dimensions, timing, safe-area, or caption policy creates a new composition version. The resolved `CompositionSpec`/`render-manifest.v1` is a separate typed contract and includes the flattened ordered IDs required by the renderer.

## 5. Timing rules

### 5.1 Source of truth

The narration/audio timing is the source of truth for scene duration after TTS
alignment. A script word-count estimate is only an early planning estimate.
The canonical timebase is the render profile's declared FPS and rational
timebase; seconds are presentation values and must not be used as a second,
independent timeline authority.

### 5.2 Scene timing

Each scene must have:

- planned duration range;
- actual audio duration;
- start/end frames;
- transition allowance;
- timing drift measurement;
- caption timing source.

### 5.3 Audio/video policy

The composition validator must reject or flag:

- gaps between required narration scenes;
- unintended overlaps;
- audio beyond cut duration;
- visuals shorter than required narration without an explicit hold policy;
- captions outside their parent scene;
- negative or non-monotonic ranges;
- transitions that exceed scene boundaries;
- timebase conversion that introduces unrecorded drift.

## 6. Captions and on-screen text

Captions are data, not merely a renderer side effect. Preserve:

- text;
- start/end frames;
- source word timestamps where applicable;
- language/locale;
- style profile;
- safe-area bounds;
- maximum line/character policy;
- text direction if localization later requires it.

Deterministic checks should measure bounding boxes against safe areas when fonts and layout are known. Rendered frame sampling should catch clipping, overlap, unreadable contrast, and accidental truncation.

## 7. Asset provenance and licensing

Every source asset records:

- source provider;
- provider asset ID;
- source URL;
- retrieval timestamp;
- content hash;
- license type;
- license URL or terms reference;
- commercial-use permission;
- attribution requirement;
- modification permission;
- prompt/model/settings for generated media;
- parent asset if derived.

The composition references an `AssetInstance` for placement. The `AssetInstance` resolves to a `SourceAsset`, which points to the immutable media `Artifact` and typed provenance. Publishing validation must be able to walk from the final cut through that chain to every source asset and its rights metadata.

## 8. Visual source types

Initial source types:

```text
stock_video
stock_image
public_domain
generated_image
generated_video
procedural_graphic
code_render
chart
diagram
text_only
```

The source type affects QC and licensing policy. A generated image still needs semantic relevance and artifact metadata. A stock clip needs rights metadata. A code render needs source/version linkage.

## 9. Audio model

Speech generation is a configurable strategy, not a fixed artifact shape. The
effective run configuration selects one of:

- `CONTINUOUS`: generate one narration or recording pass, then derive scene and
  word boundaries through ASR/forced alignment;
- `SCENE_SEGMENTED`: generate or accept one speech artifact per script scene,
  then assemble an audio manifest after scene-level checks pass.

Both strategies use the same immutable script scene manifest. The script owns
scene IDs, order, narration text, pronunciation hints, and scene boundaries;
visual planning and speech generation must not independently invent any of
those values. Each accepted speech result records the script version, a hash of
the approved narration text for every scene, voice/recording configuration, and
alignment evidence.

The scene-segmented strategy makes repair surgical:

```text
script/scene_03
  → speech_generation/scene_03
  → speech_alignment/scene_03
  → timing/scene_03
  → composition/scene_03
```

The continuous strategy preserves voice, prosody, and transition consistency in
one pass, but still requires alignment to produce scene-addressable timing. A
continuous result can therefore use the same downstream composition contract as
scene-level artifacts. If a scene is repaired after a continuous pass, policy
must choose between regenerating the affected continuous pass or switching to a
scene-segmented repair strategy with an explicit replacement and continuity
check; the system must not silently splice incompatible audio.

Audio artifacts should preserve:

- normalized input text;
- voice ID/configuration;
- provider/model/version;
- sample rate/channels;
- duration;
- loudness/peak measurements;
- ASR transcript;
- word timestamps;
- pronunciation overrides;
- generation cost/latency.

## 10. Short derivation

Short generation consumes a `quality_accepted` assembled long-form cut (the
required upstream quality gates passed) plus a short manifest. It does not
require human publication approval first; the derived short receives its own
quality gates and shares the final human publication-approval step with the
long-form package.

The manifest is the versioned `ShortSelectionManifest` contract (`short-selection.v1`), not an untyped planner note.

```json
{
  "schema_version": "short-selection.v1",
  "short_id": "short_01",
  "source_episode_id": "episode_001",
  "source_scene_ids": ["scene_04", "scene_05"],
  "hook_policy": "preserve_or_rewrite_with_review",
  "target_duration_seconds": 45,
  "aspect_ratio": "9:16",
  "reframe_policy": "vertical_safe",
  "caption_policy": "burn_in_large",
  "selected_claim_ids": ["claim_07", "claim_08"]
}
```

Shorts require separate checks for:

- hook and promise alignment;
- selected context not becoming misleading;
- vertical crop and safe areas;
- caption readability;
- independent duration/platform constraints;
- source claim preservation;
- final audio and render integrity.

## 11. Remotion boundary

Remotion components must:

- consume validated composition JSON;
- avoid provider SDKs and database access;
- avoid fetching arbitrary URLs during render;
- use only declared artifact paths/URIs resolved by the render worker;
- record renderer/template/font versions;
- produce deterministic output for the same inputs/configuration;
- fail clearly for missing/incompatible assets.

The Python render worker is responsible for:

1. resolving artifact references;
2. downloading/copying only required inputs;
3. validating checksums;
4. creating a temporary renderer manifest;
5. invoking Remotion;
6. invoking FFmpeg/ffprobe as needed;
7. uploading immutable output artifacts;
8. returning structured metadata.

## 12. Render profiles

A render profile must declare:

```yaml
schema_version: render-profile.v1
render_profile_id: landscape_1080p_30_v1
version: "1.0"
width: 1920
height: 1080
fps: 30
color_space: sRGB
pixel_format: yuv420p
video_codec: h264
container: mp4
audio_sample_rate: 48000
audio_channels: 2
audio_codec: aac
safe_area_id: default_landscape
caption_style_id: landscape_default
loudness_policy_id: youtube_default_loudness_v1
```

Do not hide platform rules in renderer code. Profiles can later include platform-specific encode variants without changing the episode model.

## 13. Composition validation

Before render:

- all artifact IDs resolve;
- all required hashes match;
- all source media decode;
- layer ranges are within cut duration;
- no illegal overlaps/gaps exist;
- z-order is unambiguous;
- text/caption references exist;
- fonts/templates exist and are versioned;
- output profile is known;
- audio tracks have compatible sample rate/channel policies;
- composition hash is stable.

After render:

- process exit status is successful;
- output decodes from start to end;
- duration and frame count are within tolerance;
- dimensions/fps/codec match profile;
- audio stream exists and is synchronized;
- black/frozen-frame and missing-audio checks run;
- frame samples around cuts/transitions/overlays are available for visual QC.

## 14. Rendering and assembly boundary

Rendering and assembly are separate workflow boundaries in the canonical graph:

1. `Rendering` consumes one resolved composition manifest and produces one or
   more immutable `RenderChunk` artifacts described by a
   `RenderChunkManifest`.
2. `Assembly` waits for the manifest's complete expected chunk set, verifies
   order, frame ranges, checksums, and continuity, and produces one immutable
   assembled-cut artifact described by an `AssemblyManifest`.
3. A chunk repair invalidates that chunk, the assembly, and only descendants of
   the affected cut. It does not invalidate unrelated cuts or source assets.

Chunk boundaries, overlap policy, and whether transitions may cross a boundary
are recorded in the chunk manifest. Assembly is not inferred from an empty
queue and is not hidden inside a renderer process for workflow purposes.

## 15. Repair boundaries

Preferred repair order:

1. layer data/config if only placement is wrong;
2. shot if visual treatment is wrong;
3. scene if narration/visual intent is wrong;
4. affected render chunk if encoding is wrong;
5. cut/master if assembly or global audio is wrong;
6. episode only when upstream editorial identity changed.

The artifact graph, not a hard-coded `if scene_03` branch, determines descendants.

## 16. Composition test fixtures

Create fixtures for:

- one scene/one shot;
- one scene/multiple shots;
- overlapping layers;
- missing asset;
- corrupt asset;
- caption outside safe area;
- audio longer than visual;
- vertical reframe;
- mixed stock/procedural assets;
- font/version mismatch;
- scene-level replacement preserving unrelated scenes;
- render chunk assembly.

## 17. Future extensions

- beat-level editorial units;
- continuous narration mode;
- presenter/avatar tracks;
- lip-sync capability;
- 3D/procedural scene graphs;
- live data charts with snapshotting;
- alternate frame rates and HDR profiles;
- multi-language localized cuts;
- adaptive short candidate selection from analytics.

These are extensions of the content/composition model, not reasons to model every frame as a workflow stage now.
