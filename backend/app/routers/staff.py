"""检测人员接口：维护检测员，覆盖安排培训、确认离岗、恢复在岗等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.staff import StaffService, VersionConflict

router = APIRouter(prefix="/api/staff", tags=["检测人员"])

service = StaffService()

LIST_FIELDS = ["员工编号", "姓名", "技术职称", "资质证书", "授权项目", "在岗状态", "考核日期", "考核结果"]
STATUSES = ["在岗", "培训中", "离岗", "停岗", "已归档"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按员工编号检索"),
    status: str | None = Query(default=None, description="在岗、培训中、离岗、停岗、已归档"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按员工编号与状态过滤检测人员列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条检测员明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"检测员 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条检测员，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="检测员已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条检测员执行状态流转；版本号对不上时返回 409，避免后提交覆盖先完成的结果。"""
    action = str(payload.values.get("action") or "").strip()
    raw_version = payload.values.get("version")
    try:
        expected_version = int(raw_version) if raw_version is not None else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="版本号必须是整数")
    try:
        entry, message = service.run_action(entry_id, action, expected_version=expected_version)
    except VersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出检测人员清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "staff", "total": total, "items": items}
