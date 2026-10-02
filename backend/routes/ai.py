"""
AI Assistant and Vision Pathologist routes for AgriSmart Connect.
Communicates directly with the local Ollama instance running llava:7b-v1.6.
Restricted to authenticated farmers only.
"""

from flask import Blueprint, request, jsonify, Response, stream_with_context

try:
    from services.ai_assistant import AgriSmartAI
    from auth_middleware import token_required, roles_required
except ImportError:
    from backend.services.ai_assistant import AgriSmartAI
    from backend.auth_middleware import token_required, roles_required

ai_bp = Blueprint('ai', __name__)


@ai_bp.route('/status', methods=['GET'])
@token_required
@roles_required('farmer', 'admin')
def get_ai_status():
    """Check whether local Ollama is online and if llava:7b-v1.6 is loaded. Farmers only."""
    status = AgriSmartAI.check_health()
    return jsonify({'status': 'success', 'ollama': status}), 200


@ai_bp.route('/chat', methods=['POST'])
@token_required
@roles_required('farmer', 'admin')
def chat_with_ai():
    """Text-based agronomy and farming advice via llava:7b-v1.6. Farmers only."""
    data = request.get_json() or {}
    message = data.get('message', '').strip()
    context = data.get('context', '')

    if not message:
        return jsonify({'error': 'Bad Request', 'message': 'Message prompt is required.'}), 400

    result = AgriSmartAI.ask_agronomy(message, context=context)
    if result.get('status') == 'error':
        return jsonify(result), 503
    return jsonify(result), 200


@ai_bp.route('/stream', methods=['POST'])
@token_required
@roles_required('farmer', 'admin')
def stream_chat():
    """
    Streaming agronomy chat via Server-Sent Events (SSE).
    Frontend receives token-by-token output from the local Ollama model.
    Each SSE event carries: data: {"token": "...", "model": "..."}\n\n
    Final event:            data: [DONE]\n\n
    """
    data = request.get_json() or {}
    message = data.get('message', '').strip()
    context = data.get('context', '')

    if not message:
        return jsonify({'error': 'Bad Request', 'message': 'Message prompt is required.'}), 400

    return Response(
        stream_with_context(AgriSmartAI.stream_agronomy(message, context=context)),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',   # Disable nginx buffering
        }
    )


@ai_bp.route('/diagnose', methods=['POST'])
@token_required
@roles_required('farmer', 'admin')
def diagnose_crop():
    """Vision-based crop pest & disease identification from uploaded leaf/plant image. Farmers only."""
    data = request.get_json() or {}
    image_base64 = data.get('image', '').strip()
    question = data.get('question', '')

    if not image_base64:
        return jsonify({'error': 'Bad Request', 'message': 'Base64 image is required.'}), 400

    result = AgriSmartAI.diagnose_crop_disease(image_base64, question=question)
    if result.get('status') == 'error':
        return jsonify(result), 503
    return jsonify(result), 200
