"""Genera el hash de contraseña para ADMIN_PASSWORD_HASH en .env.

Uso: python scripts/generate_admin_hash.py
"""
from getpass import getpass

from werkzeug.security import generate_password_hash

password = getpass("Contraseña de admin: ")
print(generate_password_hash(password))
