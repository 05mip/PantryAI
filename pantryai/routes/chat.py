from flask import Blueprint, request, jsonify, g
from services.chat import chat

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/api/chat", methods=["POST"])
def chat_endpoint():
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify(success=False, error="Message is required"), 400

    conversation_id = body.get("conversation_id")
    result = chat(g.user_id, message, conversation_id)
    return jsonify(success=True, data=result)
