import hashlib
from pathlib import Path

import pytest

from khan_agent.image_recipe import (
    ArtifactCache,
    ArtifactSourceType,
    ImageBuildStage,
    ImageRecipe,
    ImageRecipeError,
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_recipe_requires_pinned_hash_for_downloadable_artifacts():
    with pytest.raises(ImageRecipeError):
        ImageRecipe.from_dict({
            "id": "gaming-win11",
            "version": "1",
            "artifacts": [{
                "id": "khan-vdd",
                "version": "1.0.0",
                "source_type": "khan_artifact",
                "stage": "image_build",
                "url": "https://artifacts.example/khan-vdd.zip",
            }],
        })


def test_host_projection_must_be_host_specific():
    with pytest.raises(ImageRecipeError):
        ImageRecipe.from_dict({
            "id": "gaming-win11", "version": "1",
            "artifacts": [{
                "id": "nvidia-runtime", "version": "host",
                "source_type": "host_projection", "stage": "image_build",
            }],
        })


def test_cache_hit_reuses_verified_artifact(tmp_path: Path):
    data = b"khan-vdd"
    recipe = ImageRecipe.from_dict({
        "id": "gaming-win11", "version": "1",
        "artifacts": [{
            "id": "khan-vdd", "version": "1.0.0",
            "source_type": "khan_artifact", "stage": "image_build",
            "url": "https://artifacts.example/khan-vdd.zip",
            "sha256": digest(data),
        }],
    })
    artifact = recipe.artifacts[0]
    cache = ArtifactCache(tmp_path)
    path = cache.artifact_path(artifact)
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    assert cache.verify_cached(artifact) == path


def test_corrupt_cache_is_removed(tmp_path: Path):
    good = b"good"
    recipe = ImageRecipe.from_dict({
        "id": "gaming-win11", "version": "1",
        "artifacts": [{
            "id": "vcpp", "version": "14",
            "source_type": "vendor_url", "stage": "image_build",
            "url": "https://vendor.example/vcpp.exe", "sha256": digest(good),
        }],
    })
    artifact = recipe.artifacts[0]
    cache = ArtifactCache(tmp_path)
    path = cache.artifact_path(artifact)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"bad")
    assert cache.verify_cached(artifact) is None
    assert not path.exists()


def test_recipe_stage_filter_and_host_projection_deferral(tmp_path: Path):
    data = b"runtime"
    recipe = ImageRecipe.from_dict({
        "id": "gaming-win11", "version": "1",
        "artifacts": [
            {"id":"khan-runtime","version":"1","source_type":"khan_artifact","stage":"image_build","url":"https://a/r.zip","sha256":digest(data)},
            {"id":"nvidia","version":"host","source_type":"host_projection","stage":"host_specific"},
        ],
    })
    assert [a.artifact_id for a in recipe.artifacts_for_stage(ImageBuildStage.IMAGE_BUILD)] == ["khan-runtime"]
    cache = ArtifactCache(tmp_path)
    with pytest.raises(ImageRecipeError):
        cache.acquire(recipe.artifacts[1])
    receipt = tmp_path / "receipt.json"
    cache.write_receipt(recipe, receipt)
    assert "deferred_host_projection" in receipt.read_text()
