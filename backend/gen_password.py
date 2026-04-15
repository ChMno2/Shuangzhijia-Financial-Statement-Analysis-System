"""
密碼 Hash 產生工具
使用方式：python3 gen_password.py
"""
from passlib.context import CryptContext
import getpass

pwd_ctx = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

print("=== 雙之家後台 密碼 Hash 產生器 ===\n")
password = getpass.getpass("請輸入新密碼：")
confirm  = getpass.getpass("再次確認密碼：")

if password != confirm:
    print("❌ 兩次密碼不一致")
else:
    hashed = pwd_ctx.hash(password)
    print(f"\n✅ 產生成功！請將以下內容更新到 backend/.env：\n")
    print(f"ADMIN_PASSWORD_HASH={hashed}\n")
