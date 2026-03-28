import bcrypt
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import create_access_token
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.db import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    """
    Register a new user.
    ---
    tags:
      - Auth
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            email:
              type: string
            password:
              type: string
            name:
              type: string
    responses:
      201:
        description: User registered successfully
      400:
        description: Missing fields or email already exists
    """
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    name = data.get("name", "").strip()

    if not email or not password or not name:
        return jsonify({"error": "email, password and name are required"}), 400

    engine = current_app.extensions['engine']
    with Session(engine) as session:
        existing = session.scalars(select(User).where(User.email == email)).first()
        if existing:
            return jsonify({"error": "Email already registered"}), 400

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(email=email, password_hash=password_hash, name=name)
        session.add(user)
        session.commit()
        session.refresh(user)
        token = create_access_token(identity=str(user.id))

    return jsonify({"message": "Registered successfully", "token": token, "name": name}), 201


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    """
    Login with email and password.
    ---
    tags:
      - Auth
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            email:
              type: string
            password:
              type: string
    responses:
      200:
        description: Login successful, returns JWT token
      401:
        description: Invalid credentials
    """
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    engine = current_app.extensions['engine']
    with Session(engine) as session:
        user = session.scalars(select(User).where(User.email == email)).first()
        if not user or not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return jsonify({"error": "Invalid email or password"}), 401

        token = create_access_token(identity=str(user.id))
        return jsonify({"token": token, "name": user.name, "user_id": user.id})
