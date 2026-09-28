"""Needs attention (Stage 7.2): the landing list, every source in one shape.

A READ that reports. A source that cannot be read is a row in the answer,
never a failed request, so the page can say which source it could not read.
"""

import logging

from flask import Blueprint, jsonify

log = logging.getLogger(__name__)

bp = Blueprint("attention", __name__, url_prefix="/attention")


@bp.route("", methods=["GET"])
def needs_attention():
    from modules.attention import needs_attention as build
    return jsonify(build())
