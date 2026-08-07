import sys
from pathlib import Path
import pytest
from kc_installer.engine import InstallContext, CommandExecutionError, CommandExecutionResult, restart_declared_services, run_health_checks
from kc_installer.manifest import validate_manifest_files
from kc_installer.models import Manifest
from kc_installer.paths import InstallerPaths
from kc_installer.state import InstallerState


def manifest(data=None):
    base={"feature_pack":{"id":"FP-V1","name":"V1","version":"1.0.0"},"components":{}}
    if data: base.update(data)
    return Manifest.model_validate(base)


def paths(root):
    return InstallerPaths(root/'source',root,root/'runtime',root/'state',root/'backup',root/'packages')


def context(tmp_path, m):
    p=paths(tmp_path/'kc'); p.ensure_directories(); state=InstallerState(p.database_path)
    package=tmp_path/'package'; package.mkdir(exist_ok=True); target=tmp_path/'target'; target.mkdir(exist_ok=True)
    tx=state.begin(feature_pack_id='FP-V1',feature_pack_version='1.0.0',package_path=package,target_path=target,backup_path=tmp_path/'backup',dry_run=False)
    return InstallContext(package,target,m,p,state,tx,tmp_path/'backup',tmp_path/'stage',False)


def test_package_source_cannot_escape_root(tmp_path):
    package=tmp_path/'package'; package.mkdir(); (tmp_path/'outside').write_text('x')
    m=manifest({"components":{"x":{"enabled":True,"source":"../outside","destination":"x"}}})
    assert any('escapes package root' in e for e in validate_manifest_files(package,m))


def test_destination_cannot_be_absolute(tmp_path):
    package=tmp_path/'package'; package.mkdir(); (package/'x').write_text('x')
    m=manifest({"components":{"x":{"enabled":True,"source":"x","destination":"/etc/x"}}})
    assert any('target-relative' in e for e in validate_manifest_files(package,m))


def test_destination_cannot_traverse_parent(tmp_path):
    package=tmp_path/'package'; package.mkdir(); (package/'x').write_text('x')
    m=manifest({"components":{"x":{"enabled":True,"source":"x","destination":"../x"}}})
    assert any('target-relative' in e for e in validate_manifest_files(package,m))


def test_health_success_is_persisted(tmp_path):
    m=manifest({"health_checks":[{"type":"command","name":"ok","command":[sys.executable,"-c","print('healthy')"]}]})
    c=context(tmp_path,m); run_health_checks(c)
    rows=c.state.health_check_results(c.transaction_id)
    assert rows[0]['status']=='success' and 'healthy' in rows[0]['stdout']


def test_health_failure_is_persisted(tmp_path):
    m=manifest({"health_checks":[{"type":"command","name":"bad","command":[sys.executable,"-c","import sys; print('bad'); sys.exit(3)"]}]})
    c=context(tmp_path,m)
    with pytest.raises(CommandExecutionError): run_health_checks(c)
    rows=c.state.health_check_results(c.transaction_id)
    assert rows[0]['status']=='failed' and rows[0]['return_code']==3


def test_service_restart_disabled_does_nothing(tmp_path, monkeypatch):
    m=manifest({"operations":{"restart_services":False,"services":[{"name":"demo.service"}]}}); c=context(tmp_path,m)
    monkeypatch.setattr('kc_installer.engine.execute_command', lambda *a,**k: (_ for _ in ()).throw(AssertionError('called')))
    restart_declared_services(c)


def test_service_restart_and_verification(tmp_path, monkeypatch):
    m=manifest({"operations":{"restart_services":True,"services":[{"name":"demo.service"}]}}); c=context(tmp_path,m); calls=[]
    def fake(cmd, **kwargs):
        calls.append(cmd); return CommandExecutionResult(cmd,0,'','')
    monkeypatch.setattr('kc_installer.engine.execute_command', fake)
    restart_declared_services(c)
    assert calls==[['systemctl','restart','demo.service'],['systemctl','is-active','--quiet','demo.service']]


def test_invalid_service_name_is_rejected(tmp_path):
    m=manifest({"operations":{"restart_services":True,"services":[{"name":"bad service"}]}}); c=context(tmp_path,m)
    with pytest.raises(Exception, match='Invalid service name'): restart_declared_services(c)


def test_release_version_is_1_0():
    import tomllib
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert project["project"]["version"] == "1.0.0"
