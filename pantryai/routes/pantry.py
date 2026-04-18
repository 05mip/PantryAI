from flask import Blueprint, request, jsonify, g

from services.dynamo import (
    list_pantry, add_pantry_item, update_pantry_item,
    delete_pantry_item, bulk_add_pantry, get_pantry_categories,
)

pantry_bp = Blueprint("pantry", __name__, url_prefix="/api/pantry")


@pantry_bp.route("", methods=["GET"])
def get_pantry():
    items = list_pantry(g.user_id)
    return jsonify({"success": True, "data": items})


@pantry_bp.route("", methods=["POST"])
def create_item():
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"success": False, "error": "Name is required"}), 400

    item = add_pantry_item(
        user_id=g.user_id,
        name=data["name"],
        quantity=data.get("quantity", 1),
        unit=data.get("unit", "count"),
        category=data.get("category", "other"),
        expiry_date=data.get("expiry_date"),
    )
    return jsonify({"success": True, "data": item}), 201


@pantry_bp.route("/<item_id>", methods=["PUT"])
def update_item(item_id):
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No update data provided"}), 400

    item = update_pantry_item(g.user_id, item_id, data)
    if not item:
        return jsonify({"success": False, "error": "Item not found"}), 404
    return jsonify({"success": True, "data": item})


@pantry_bp.route("/<item_id>", methods=["DELETE"])
def remove_item(item_id):
    delete_pantry_item(g.user_id, item_id)
    return jsonify({"success": True, "data": {"deleted": item_id}})


@pantry_bp.route("/bulk", methods=["POST"])
def bulk_add():
    data = request.get_json()
    if not data or not isinstance(data, list):
        return jsonify({"success": False, "error": "Expected a list of items"}), 400

    results = bulk_add_pantry(g.user_id, data)
    return jsonify({"success": True, "data": results}), 201


@pantry_bp.route("/categories", methods=["GET"])
def categories():
    cats = get_pantry_categories(g.user_id)
    return jsonify({"success": True, "data": cats})
