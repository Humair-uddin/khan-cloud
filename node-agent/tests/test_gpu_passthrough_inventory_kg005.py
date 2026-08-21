from pathlib import Path

def test_inventory_exposes_gpu_passthrough_contract():
    root=Path(__file__).resolve().parents[1]; src=(root/"khan_agent/inventory.py").read_text()
    assert "def _gpu_passthrough_inventory" in src
    assert '"gpu_passthrough": _gpu_passthrough_inventory()' in src
    assert '"assignable"' in src and '"iommu_group"' in src and '"vfio-pci"' in src
