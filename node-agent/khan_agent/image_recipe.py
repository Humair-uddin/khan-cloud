from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from khan_agent.provisioning import ArtifactSpec, ResumableArtifactDownloader


class ImageRecipeError(RuntimeError):
    pass


class ArtifactSourceType(StrEnum):
    VENDOR_URL = "vendor_url"
    KHAN_ARTIFACT = "khan_artifact"
    LOCAL_CACHE = "local_cache"
    HOST_PROJECTION = "host_projection"


class ImageBuildStage(StrEnum):
    WINDOWS_SOURCE = "windows_source"
    IMAGE_BUILD = "image_build"
    POST_DEPLOY = "post_deploy"
    HOST_SPECIFIC = "host_specific"
    SESSION = "session"


@dataclass(frozen=True)
class RecipeArtifact:
    artifact_id: str
    version: str
    source_type: ArtifactSourceType
    stage: ImageBuildStage
    sha256: str = ""
    url: str = ""
    architecture: str = "any"
    license: str = ""
    signer: str = ""
    total_bytes: int = 0
    install: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RecipeArtifact":
        artifact_id = str(raw.get("id") or raw.get("artifact_id") or "").strip()
        version = str(raw.get("version") or "").strip()
        if not artifact_id:
            raise ImageRecipeError("Artifact id is required.")
        if not version:
            raise ImageRecipeError(f"Artifact {artifact_id!r} version is required.")
        try:
            source_type = ArtifactSourceType(str(raw.get("source_type") or ""))
        except ValueError as exc:
            raise ImageRecipeError(f"Artifact {artifact_id!r} has invalid source_type.") from exc
        try:
            stage = ImageBuildStage(str(raw.get("stage") or ""))
        except ValueError as exc:
            raise ImageRecipeError(f"Artifact {artifact_id!r} has invalid stage.") from exc

        url = str(raw.get("url") or "").strip()
        sha256 = str(raw.get("sha256") or "").strip().lower()
        if source_type in {ArtifactSourceType.VENDOR_URL, ArtifactSourceType.KHAN_ARTIFACT}:
            if not url:
                raise ImageRecipeError(f"Artifact {artifact_id!r} requires a URL.")
            if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
                raise ImageRecipeError(f"Artifact {artifact_id!r} requires a pinned SHA-256.")
        if source_type is ArtifactSourceType.HOST_PROJECTION and stage is not ImageBuildStage.HOST_SPECIFIC:
            raise ImageRecipeError(
                f"Host-projected artifact {artifact_id!r} must use host_specific stage."
            )

        return cls(
            artifact_id=artifact_id,
            version=version,
            source_type=source_type,
            stage=stage,
            sha256=sha256,
            url=url,
            architecture=str(raw.get("architecture") or "any"),
            license=str(raw.get("license") or ""),
            signer=str(raw.get("signer") or ""),
            total_bytes=max(0, int(raw.get("total_bytes") or 0)),
            install=dict(raw.get("install") or {}),
            validation=dict(raw.get("validation") or {}),
        )


@dataclass(frozen=True)
class ImageRecipe:
    recipe_id: str
    version: str
    windows: dict[str, Any]
    artifacts: tuple[RecipeArtifact, ...]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ImageRecipe":
        recipe_id = str(raw.get("id") or raw.get("recipe_id") or "").strip()
        version = str(raw.get("version") or "").strip()
        if not recipe_id or not version:
            raise ImageRecipeError("Image recipe id and version are required.")
        artifacts = tuple(RecipeArtifact.from_dict(item) for item in raw.get("artifacts", []))
        ids = [item.artifact_id for item in artifacts]
        if len(ids) != len(set(ids)):
            raise ImageRecipeError("Image recipe artifact ids must be unique.")
        return cls(
            recipe_id=recipe_id,
            version=version,
            windows=dict(raw.get("windows") or {}),
            artifacts=artifacts,
        )

    @classmethod
    def load(cls, path: Path) -> "ImageRecipe":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def artifacts_for_stage(self, stage: ImageBuildStage) -> tuple[RecipeArtifact, ...]:
        return tuple(item for item in self.artifacts if item.stage is stage)


class ArtifactCache:
    """Deterministic cache for pinned image-recipe artifacts.

    Downloadable artifacts are accepted only when their SHA-256 matches the recipe.
    Host-projected artifacts are never downloaded into the generic image cache.
    """

    def __init__(self, root: Path, *, downloader: ResumableArtifactDownloader | None = None) -> None:
        self.root = Path(root)
        self.downloader = downloader or ResumableArtifactDownloader()

    @staticmethod
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def artifact_path(self, artifact: RecipeArtifact) -> Path:
        suffix = Path(artifact.url).name if artifact.url else "payload.bin"
        safe_name = suffix or "payload.bin"
        return self.root / artifact.artifact_id / artifact.version / safe_name

    def verify_cached(self, artifact: RecipeArtifact) -> Path | None:
        if artifact.source_type is ArtifactSourceType.HOST_PROJECTION:
            return None
        path = self.artifact_path(artifact)
        if not path.is_file():
            return None
        if artifact.sha256 and self.sha256(path).lower() != artifact.sha256.lower():
            path.unlink(missing_ok=True)
            return None
        return path

    def acquire(self, artifact: RecipeArtifact, *, on_progress=None) -> Path:
        if artifact.source_type is ArtifactSourceType.HOST_PROJECTION:
            raise ImageRecipeError(
                f"Artifact {artifact.artifact_id!r} is host-projected and cannot be downloaded."
            )
        cached = self.verify_cached(artifact)
        if cached is not None:
            return cached
        if artifact.source_type is ArtifactSourceType.LOCAL_CACHE:
            raise ImageRecipeError(
                f"Required local-cache artifact {artifact.artifact_id!r} is missing or invalid."
            )
        destination = self.artifact_path(artifact)
        spec = ArtifactSpec(
            artifact_id=artifact.artifact_id,
            url=artifact.url,
            destination=destination,
            sha256=artifact.sha256,
            total_bytes=artifact.total_bytes,
        )
        return self.downloader.download(spec, on_progress=on_progress)

    def write_receipt(self, recipe: ImageRecipe, path: Path) -> None:
        records = []
        for artifact in recipe.artifacts:
            if artifact.source_type is ArtifactSourceType.HOST_PROJECTION:
                status = "deferred_host_projection"
                cached_path = None
            else:
                cached = self.verify_cached(artifact)
                status = "verified" if cached else "missing"
                cached_path = str(cached) if cached else None
            records.append({
                "id": artifact.artifact_id,
                "version": artifact.version,
                "source_type": artifact.source_type.value,
                "stage": artifact.stage.value,
                "status": status,
                "path": cached_path,
                "sha256": artifact.sha256,
            })
        payload = {
            "recipe_id": recipe.recipe_id,
            "recipe_version": recipe.version,
            "artifacts": records,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        temp = Path(path).with_suffix(Path(path).suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, path)
