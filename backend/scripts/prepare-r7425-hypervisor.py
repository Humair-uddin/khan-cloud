#!/usr/bin/env python3
from __future__ import annotations
import shutil, tempfile, zipfile
from pathlib import Path
from sqlalchemy import select
from app.db.database import SessionLocal
from app.models.node import Node
from app.models.user import User
from app.services.node_service import transition_node

NODE_NAME="KC-R7425-VPS-01"
OUTPUT=Path("/tmp/khan-cloud-r7425-hypervisor-activate.zip")

def main():
    with SessionLocal() as db:
        actor=db.scalar(select(User).where(User.username=="humair-uddin"))
        if actor is None: raise RuntimeError("humair-uddin user not found")
        node=db.scalar(select(Node).where(Node.name==NODE_NAME))
        if node is None: raise RuntimeError("R7425 node not found")
        if node.lifecycle_state=="pending_approval":
            transition_node(db,node=node,new_state="approved",actor_user_id=actor.id,reason="R7425 hypervisor activation")
        elif node.lifecycle_state!="approved":
            raise RuntimeError(f"Unexpected R7425 lifecycle: {node.lifecycle_state}")
        node_id=str(node.id)

    source=Path("/opt/khan-cloud/source/node-agent")
    with tempfile.TemporaryDirectory(prefix="kc-r7425-hv-") as td:
        stage=Path(td)/"khan-cloud-r7425-hypervisor-activate"
        (stage/"node-agent").mkdir(parents=True)
        shutil.copytree(source/"khan_agent",stage/"node-agent"/"khan_agent")
        shutil.copy2(source/"requirements.txt",stage/"node-agent"/"requirements.txt")
        shutil.copy2(source/"systemd/khan-cloud-agent.service",stage/"khan-cloud-agent.service")
        shutil.copy2(Path(__file__).resolve().parents[2]/"node-agent/deploy/activate-r7425-hypervisor.sh",stage/"activate.sh")
        (stage/"NODE_ID").write_text(node_id+"\n")
        if OUTPUT.exists(): OUTPUT.unlink()
        with zipfile.ZipFile(OUTPUT,"w",zipfile.ZIP_DEFLATED) as z:
            for p in stage.rglob("*"):
                if p.is_file(): z.write(p,p.relative_to(stage.parent))
    OUTPUT.chmod(0o600)
    print("R7425 node approved:", node_id)
    print("Activation bundle:", OUTPUT)

if __name__=="__main__": main()
