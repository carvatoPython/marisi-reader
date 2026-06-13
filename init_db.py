#!/usr/bin/env python3
"""Run this once before starting the server to initialize the database."""
from app import app, init_db
with app.app_context():
    init_db()
    print("✓ Base de datos inicializada correctamente.")
    print("✓ Marisi Reader listo.")
