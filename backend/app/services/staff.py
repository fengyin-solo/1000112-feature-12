"""检测人员业务规则：在岗状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "staff"
REQUIRED_FIELDS = ["员工编号", "姓名", "技术职称"]
STATUS_ORDER = ["在岗", "培训中", "离岗", "停岗", "已归档"]

# 状态流转规则：动作 -> (允许的当前状态, 目标状态)。
# 只有当前状态在允许集合里，动作才会出现在记录的可执行动作中。
TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "安排培训": (frozenset({"在岗"}), "培训中"),
    "恢复在岗": (frozenset({"培训中", "离岗"}), "在岗"),
    "退回": (frozenset({"培训中"}), "在岗"),
    "确认离岗": (frozenset({"在岗", "培训中"}), "离岗"),
    "归档": (frozenset({"离岗"}), "已归档"),
}

# 处于这些状态时视为「待处理」，汇总到看板的待处理卡片。
PENDING_STATUSES = {"培训中", "离岗"}


class VersionConflict(Exception):
    """提交基于旧版本记录：先完成的修改不允许被后提交的覆盖。"""


def _version_of(row: dict[str, Any]) -> int:
    """老数据没有版本号，按 1 处理，保证原有记录不受影响。"""
    return int(row.get("version") or 1)


def available_actions(status: str) -> list[str]:
    """按当前状态计算可执行动作，列表、明细与动作结果共用同一份流转规则。"""
    return [action for action, (sources, _) in TRANSITIONS.items() if status in sources]


def _present(row: dict[str, Any]) -> dict[str, Any]:
    """输出副本：附带版本号与可执行动作，不回写仓库，避免残留旧状态。"""
    return {
        **row,
        "version": _version_of(row),
        "available_actions": available_actions(str(row.get("status") or "")),
    }


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
        return [_present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return _present(row) if row is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["在岗状态"] = STATUS_ORDER[0]
        entry["pending"] = STATUS_ORDER[0] in PENDING_STATUSES
        entry["abnormal"] = False
        entry["version"] = 1
        rows.append(entry)
        return _present(entry), []

    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        expected_version: int | None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测员 {entry_id} 不存在或已归档"
        if action not in TRANSITIONS:
            return None, f"动作「{action}」不属于检测人员可执行范围"
        current_version = _version_of(entry)
        if expected_version != current_version:
            raise VersionConflict(
                f"检测员 {entry_id} 已被他人更新（当前状态：{entry.get('status')}），请刷新后重试"
            )
        sources, target = TRANSITIONS[action]
        status = str(entry.get("status") or "")
        if status not in sources:
            allowed = "、".join(available_actions(status)) or "无"
            return None, f"当前状态「{status}」不能执行「{action}」，可执行动作：{allowed}"
        entry["status"] = target
        entry["在岗状态"] = target
        entry["pending"] = target in PENDING_STATUSES
        entry["abnormal"] = False
        entry["version"] = current_version + 1
        return _present(entry), f"检测员已{action}，当前状态：{target}"
