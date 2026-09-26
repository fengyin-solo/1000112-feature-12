"""检测人员业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "staff"
REQUIRED_FIELDS = ["员工编号", "姓名", "技术职称"]
STATUS_ORDER = ["在岗", "培训中", "离岗", "停岗"]
ACTION_RULES = {"安排培训": "培训中", "确认离岗": "离岗", "恢复在岗": "在岗"}
NEGATIVE_ACTIONS = []

# 状态机：每个状态当前可见、可执行的动作；不在列表里的动作一律拦下。
# 停岗是归档态，不再暴露任何动作，恢复在岗只能回到离岗前的在册流程。
STATUS_ACTIONS = {
    "在岗": ["安排培训", "确认离岗"],
    "培训中": ["恢复在岗", "确认离岗"],
    "离岗": ["恢复在岗"],
    "停岗": [],
}


def available_actions(entry: dict[str, Any]) -> list[str]:
    """按当前状态计算可见动作；未知状态不暴露任何按钮，避免残留旧入口。"""
    return list(STATUS_ACTIONS.get(str(entry.get("status") or ""), []))


def entry_version(entry: dict[str, Any]) -> int:
    """读取记录版本号；老数据没有 version 字段时按 1 处理，不影响正常记录。"""
    try:
        return int(entry.get("version") or 1)
    except (TypeError, ValueError):
        return 1


class StaffService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("员工编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._decorate(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._decorate(entry)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["version"] = 1
        rows.append(entry)
        return self._decorate(entry), []

    def run_action(
        self,
        entry_id: int,
        action: str,
        version: int | None,
    ) -> tuple[dict[str, Any] | None, str, int]:
        """执行状态动作，返回 (记录, 说明, HTTP 状态码)。

        version 是调用方看到的记录版本号：不一致说明有人先改过了，
        返回 409 让后提交者刷新，而不是覆盖先完成的结果。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测员 {entry_id} 不存在或已归档", 404
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于检测人员可执行范围", 400
        current = str(entry.get("status") or "")
        if action not in STATUS_ACTIONS.get(current, []):
            return None, f"检测员当前为「{current}」，不能执行「{action}」", 409
        if version is None:
            return None, "缺少记录版本号，请刷新列表后重试", 400
        if version != entry_version(entry):
            return None, "该检测员刚被他人变更，请刷新后基于最新状态再操作", 409
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里", 400
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        entry["version"] = entry_version(entry) + 1
        return self._decorate(entry), f"检测员已{action}", 200

    def _decorate(self, entry: dict[str, Any]) -> dict[str, Any]:
        """输出前补上版本号与可见动作；用副本，不把派生字段写回仓库。"""
        view = dict(entry)
        view["version"] = entry_version(entry)
        view["available_actions"] = available_actions(entry)
        return view
