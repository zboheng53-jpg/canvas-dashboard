"""Shared validation for human and Agent writes; stored legacy text stays intact."""
from datetime import date
import hashlib
import json


class ActionValidationError(ValueError):
    pass


class ActionConflictError(ValueError):
    pass


def short_title(value):
    if not isinstance(value, str) or not value.strip():
        raise ActionValidationError("请填写简短的事项标题")
    value = value.strip()
    if len(value) > 40 or "\n" in value:
        raise ActionValidationError("标题最多 40 字；步骤、材料和背景请放入详情 details")
    return value


def action_fields(data):
    """Validate only supplied fields so partial updates cannot clear other values."""
    result = {}
    for field, limit in (("details", 12000), ("materials", 20000)):
        if field in data:
            value = data[field]
            if not isinstance(value, str) or len(value) > limit:
                raise ActionValidationError(f"{field} 必须是最多 {limit} 字的文本")
            result[field] = value.strip()
    if "commitment" in data:
        if data["commitment"] not in ("obligation", "growth"):
            raise ActionValidationError("commitment 请选择 obligation（责任）或 growth（成长）")
        result["commitment"] = data["commitment"]
    for field in ("due_date", "planned_on"):
        if field in data:
            value = data[field]
            try:
                result[field] = date.fromisoformat(value).isoformat() if value else None
            except (TypeError, ValueError):
                raise ActionValidationError(f"{field} 请使用 YYYY-MM-DD；未知日期请留空") from None
    if "estimate_minutes" in data:
        value = data["estimate_minutes"]
        if value is not None and (type(value) is not int or not 1 <= value <= 1440):
            raise ActionValidationError("预计时长请填写 1–1440 分钟，或留空")
        result["estimate_minutes"] = value
    for field in ("request_id", "expected_updated_at"):
        if field in data:
            value = data[field]
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                raise ActionValidationError(f"{field} 必须是非空短文本")
            result[field] = value.strip()
    return result


def fingerprint(payload):
    value = {k: v for k, v in payload.items() if k not in ("request_id", "expected_updated_at")}
    if value.get("action_ref"):
        value.pop("title", None)  # A linked title may change between a write and its retry.
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def replay(items, payload):
    request_id = payload.get("request_id")
    if request_id:
        item = next((item for item in items if item.get("request_id") == request_id), None)
        if item:
            if item.get("request_fingerprint") != fingerprint(payload):
                raise ActionConflictError("此 request_id 已用于不同内容；请读取已保存事项或使用新的请求标识")
            return item
    return None


def check_version(item, changes):
    expected = changes.get("expected_updated_at")
    if expected and item.get("updated_at") != expected:
        raise ActionConflictError("事项已被修改，请重新读取详情后再提交")
