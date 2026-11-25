
from flask import (
    Flask, request, jsonify, send_from_directory, session
)
from functools import wraps
from uuid import uuid4
import hashlib
import hmac
import ipaddress
import os
import secrets
import socket
import sys
import time

# Security settings must be configured in the hosting environment.
SECRET_KEY = os.environ.get("SECRET_KEY", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

if len(SECRET_KEY) < 32:
    raise RuntimeError("Set SECRET_KEY to a random value of at least 32 characters.")

if len(ADMIN_PASSWORD) < 16:
    raise RuntimeError("Set ADMIN_PASSWORD to a strong password of at least 16 characters.")

app = Flask(__name__)
app.secret_key = SECRET_KEY

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get(
        "SESSION_COOKIE_SECURE", "true"
    ).lower() == "true",
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=8 * 60 * 60
)

# Projector credentials are held in server memory only.
projectors = {}

SUPPORTED_BRANDS = {
    "Epson", "BenQ", "Sony", "Panasonic",
    "Optoma", "ViewSonic", "Other"
}
PJLINK_PORT = 4352
SOCKET_TIMEOUT = 3.0

# Basic per-process login throttling.
login_attempts = {}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60


class ProjectorError(Exception):
    pass


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def check_csrf():
    supplied = request.headers.get("X-CSRF-Token", "")
    expected = session.get("csrf_token", "")
    return bool(expected and supplied and hmac.compare_digest(supplied, expected))


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("authenticated"):
            return jsonify(success=False, message="Please log in first."), 401
        return fn(*args, **kwargs)
    return wrapper


def require_csrf(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not check_csrf():
            return jsonify(success=False, message="Security token expired. Refresh the page and log in again."), 403
        return fn(*args, **kwargs)
    return wrapper


def login_rate_limited():
    key = request.remote_addr or "unknown"
    now = time.monotonic()

    attempts = [
        stamp for stamp in login_attempts.get(key, [])
        if now - stamp < LOGIN_WINDOW_SECONDS
    ]
    login_attempts[key] = attempts

    if len(attempts) >= MAX_LOGIN_ATTEMPTS:
        return True

    attempts.append(now)
    login_attempts[key] = attempts
    return False


def read_line(sock):
    data = bytearray()
    while len(data) < 1024:
        chunk = sock.recv(1)
        if not chunk:
            break
        data.extend(chunk)
        if chunk == b"\n":
            break
    if not data:
        raise ProjectorError("Projector closed the connection without a response.")
    return data.decode("ascii", errors="replace").strip()


def validate_private_ip(value):
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        raise ProjectorError("Enter a valid IP address.")

    if not (address.is_private or address.is_link_local):
        raise ProjectorError("For safety, enter the projector's private/local network IP address.")
    if address.is_loopback or address.is_multicast or address.is_unspecified:
        raise ProjectorError("That IP address is not a valid projector destination.")
    return str(address)


def pjlink_command(ip, password, command):
    ip = validate_private_ip(ip)

    try:
        with socket.create_connection(
            (ip, PJLINK_PORT), timeout=SOCKET_TIMEOUT
        ) as sock:
            sock.settimeout(SOCKET_TIMEOUT)
            greeting = read_line(sock)

            if greeting.startswith("PJLINK 0"):
                payload = command + "\r"
            elif greeting.startswith("PJLINK 1 "):
                challenge = greeting[len("PJLINK 1 "):].strip()
                if not challenge:
                    raise ProjectorError("Projector sent an invalid PJLink authentication challenge.")
                digest = hashlib.md5(
                    (password + challenge).encode("utf-8")
                ).hexdigest()
                payload = digest + command + "\r"
            elif greeting.startswith("PJLINK ERRA"):
                raise ProjectorError("PJLink authentication is locked or unavailable.")
            else:
                raise ProjectorError("The device did not identify itself as a PJLink projector.")

            sock.sendall(payload.encode("ascii"))
            response = read_line(sock)

            if "ERRA" in response:
                raise ProjectorError("PJLink authentication failed. Check the projector password.")
            if "ERR1" in response:
                raise ProjectorError("PJLink: unsupported command.")
            if "ERR2" in response:
                raise ProjectorError("PJLink: out-of-parameter error.")
            if "ERR3" in response:
                raise ProjectorError("PJLink: projector is busy.")
            if "ERR4" in response:
                raise ProjectorError("PJLink: projector reports a device failure.")
            if not response.startswith("%1"):
                raise ProjectorError("Unexpected response from projector.")
            return response

    except socket.timeout:
        raise ProjectorError("Connection timed out. Check IP, network route and projector network-control settings.")
    except ConnectionRefusedError:
        raise ProjectorError("Connection refused. PJLink may be disabled or unavailable.")
    except OSError as exc:
        raise ProjectorError(f"Network connection failed: {exc.strerror or str(exc)}")


def get_power_state(ip, password):
    response = pjlink_command(ip, password, "%1POWR ?")
    if "=" not in response:
        raise ProjectorError("Could not understand the projector power-status response.")

    value = response.split("=", 1)[1].strip()
    states = {
        "0": "STANDBY",
        "1": "ON",
        "2": "COOLING",
        "3": "WARMING"
    }
    if value not in states:
        raise ProjectorError(f"Unknown projector power state: {value}")
    return states[value]


def public_projector(item):
    return {
        "id": item["id"],
        "name": item["name"],
        "brand": item["brand"],
        "model": item["model"],
        "ip": item["ip"],
        "protocol": "PJLink Class 1",
        "connection": item["connection"],
        "power": item["power"]
    }


@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    if filename in ("style.css", "script.js"):
        return send_from_directory(".", filename)
    return "Not found", 404


# Public authentication status endpoint.
@app.get("/api/auth/status")
def auth_status():
    return jsonify(
        authenticated=bool(session.get("authenticated")),
        csrf_token=csrf_token()
    )


@app.post("/api/login")
@require_csrf
def login():
    if login_rate_limited():
        return jsonify(
            success=False,
            message="Too many login attempts. Try again in 15 minutes."
        ), 429

    data = request.get_json(silent=True) or {}
    supplied_password = str(data.get("password", ""))

    if not hmac.compare_digest(supplied_password, ADMIN_PASSWORD):
        return jsonify(success=False, message="Incorrect admin password."), 401

    session.clear()
    session.permanent = True
    session["authenticated"] = True

    return jsonify(
        success=True,
        message="Login successful.",
        csrf_token=csrf_token()
    )


@app.post("/api/logout")
@require_auth
@require_csrf
def logout():
    session.clear()
    return jsonify(success=True, message="Logged out successfully.")


@app.get("/api/projectors")
@require_auth
def list_projectors():
    return jsonify([
        public_projector(p) for p in projectors.values()
    ])


@app.post("/api/projectors")
@require_auth
@require_csrf
def add_projector():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    brand = str(data.get("brand", "")).strip()
    model = str(data.get("model", "")).strip()
    ip = str(data.get("ip", "")).strip()
    password = str(data.get("password", ""))

    if not name:
        return jsonify(success=False, message="Enter a projector name."), 400
    if brand not in SUPPORTED_BRANDS:
        return jsonify(success=False, message="Select a supported brand."), 400
    if not model:
        return jsonify(success=False, message="Enter the exact projector model, if known."), 400

    try:
        ip = validate_private_ip(ip)
    except ProjectorError as exc:
        return jsonify(success=False, message=str(exc)), 400

    projector_id = str(uuid4())
    item = {
        "id": projector_id,
        "name": name,
        "brand": brand,
        "model": model,
        "ip": ip,
        "password": password,
        "connection": "NOT TESTED",
        "power": "UNKNOWN"
    }
    projectors[projector_id] = item

    return jsonify(
        success=True,
        message="Projector profile saved in server memory. Test the PJLink connection next.",
        projector=public_projector(item)
    ), 201


@app.post("/api/projectors/<projector_id>/connect")
@require_auth
@require_csrf
def connect_projector(projector_id):
    item = projectors.get(projector_id)
    if item is None:
        return jsonify(success=False, message="Projector profile not found."), 404

    try:
        state = get_power_state(item["ip"], item["password"])
        item["connection"] = "CONNECTED"
        item["power"] = state
        return jsonify(
            success=True,
            message="PJLink connection verified.",
            projector=public_projector(item)
        )
    except ProjectorError as exc:
        item["connection"] = "FAILED"
        item["power"] = "UNKNOWN"
        return jsonify(
            success=False,
            message=str(exc),
            projector=public_projector(item)
        ), 502


@app.post("/api/projectors/<projector_id>/power")
@require_auth
@require_csrf
def power_projector(projector_id):
    item = projectors.get(projector_id)
    if item is None:
        return jsonify(success=False, message="Projector profile not found."), 404

    data = request.get_json(silent=True) or {}
    action = str(data.get("action", "")).upper()

    if action not in ("ON", "OFF"):
        return jsonify(success=False, message="Action must be ON or OFF."), 400

    command_value = "1" if action == "ON" else "0"

    try:
        response = pjlink_command(
            item["ip"], item["password"], f"%1POWR {command_value}"
        )
        state = get_power_state(item["ip"], item["password"])
        expected = "ON" if action == "ON" else "STANDBY"

        item["connection"] = "CONNECTED"
        item["power"] = state

        if state != expected:
            return jsonify(
                success=False,
                message=f"Command was acknowledged, but verified state is {state}.",
                projector=public_projector(item),
                response=response
            ), 502

        return jsonify(
            success=True,
            message=f"Real projector power state verified: {state}.",
            projector=public_projector(item),
            response=response
        )

    except ProjectorError as exc:
        item["connection"] = "FAILED"
        item["power"] = "UNKNOWN"
        return jsonify(
            success=False,
            message=str(exc),
            projector=public_projector(item)
        ), 502


@app.delete("/api/projectors/<projector_id>")
@require_auth
@require_csrf
def delete_projector(projector_id):
    if projector_id not in projectors:
        return jsonify(success=False, message="Projector profile not found."), 404

    del projectors[projector_id]
    return jsonify(
        success=True,
        message="Projector profile and in-memory credentials cleared."
    )


if __name__ == "__main__":
    host = "127.0.0.1"
    if "--lan" in sys.argv:
        host = "0.0.0.0"
        print("WARNING: LAN mode exposes this dashboard to your local network.")

    print("Universal Projector Remote starting...")
    app.run(host=host, port=5000, debug=False)
