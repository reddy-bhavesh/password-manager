from __future__ import annotations

import datetime
import uuid

from app.models.folder import Folder
from app.services.vault import _build_folder_tree


def _make_folder(
    *,
    folder_id: uuid.UUID,
    owner_id: uuid.UUID,
    org_id: uuid.UUID,
    name: str,
    parent_folder_id: uuid.UUID | None = None,
) -> Folder:
    return Folder(
        id=folder_id,
        owner_id=owner_id,
        org_id=org_id,
        parent_folder_id=parent_folder_id,
        name=name,
        created_at=datetime.datetime.now(datetime.UTC),
    )


def test_build_folder_tree_nests_children_under_parent() -> None:
    owner_id = uuid.uuid4()
    org_id = uuid.uuid4()
    root_id = uuid.uuid4()
    child_id = uuid.uuid4()
    orphan_id = uuid.uuid4()

    folders = [
        _make_folder(folder_id=child_id, owner_id=owner_id, org_id=org_id, name="Child", parent_folder_id=root_id),
        _make_folder(folder_id=root_id, owner_id=owner_id, org_id=org_id, name="Root"),
        _make_folder(folder_id=orphan_id, owner_id=owner_id, org_id=org_id, name="Orphan"),
    ]

    tree = _build_folder_tree(folders)

    assert len(tree) == 2
    root = next(node for node in tree if str(node.id) == str(root_id))
    orphan = next(node for node in tree if str(node.id) == str(orphan_id))

    assert root.name == "Root"
    assert len(root.children) == 1
    assert str(root.children[0].id) == str(child_id)
    assert orphan.children == []
