"""Shared material-log endpoints; each mutation holds the existing project lock."""
import project_store
from flask import jsonify, request
from web_common import api_error, invalid_request_response, read_json_request


def materials_response(username):
    project_id = request.args.get("project_id")
    if project_id is not None:
        try:
            project_id = int(project_id)
            if project_id < 1:
                raise ValueError
        except ValueError:
            return invalid_request_response()
    result = project_store.material_log(username, project_id=project_id)
    if project_id is not None and not result["projects"]:
        return api_error("project_not_found", "项目不存在", 404)
    return jsonify(ok=True, **result)


def material_write_response(username, project_id, entry_id=None, today=None):
    payload = read_json_request()
    if payload is None:
        return invalid_request_response()
    if entry_id is None:
        entry = project_store.create_material_entry(username, project_id, payload, today=today)
    else:
        entry = project_store.update_material_entry(username, project_id, entry_id, payload,
                                                    delete=request.method == "DELETE")
    if entry is None:
        return api_error("material_not_found", "项目或资料不存在", 404)
    return jsonify(ok=True, entry=entry)
