import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.database import users_collection
from services.auth import get_password_hash, get_user_by_email
from datetime import datetime
from utils.logging import log_info, log_warning, log_error


async def create_admin_user(email, password, full_name="Admin User"):
    # Check if user already exists
    existing_user = await get_user_by_email(email)

    if existing_user:
        if existing_user.get("role") == "admin":
            log_info(
                f"Admin user {email} already exists.", "create_admin", {"email": email}
            )
            return

        # Update existing user to admin
        await users_collection.update_one(
            {"email": email},
            {"$set": {"role": "admin", "updated_at": datetime.utcnow()}},
        )
        log_info(
            f"User {email} updated to admin role.", "create_admin", {"email": email}
        )
        return

    # Create new admin user
    hashed_password = get_password_hash(password)
    admin_user = {
        "email": email,
        "password": hashed_password,
        "full_name": full_name,
        "role": "admin",
        "status": "active",
        "created_at": datetime.utcnow(),
    }

    await users_collection.insert_one(admin_user)
    log_info(
        f"Admin user {email} created successfully.", "create_admin", {"email": email}
    )


async def main():
    # Get admin credentials from environment or use defaults
    admin_email = os.getenv("ADMIN_EMAIL", "admin@voicera.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")  # Change in production!
    admin_name = os.getenv("ADMIN_NAME", "System Administrator")

    try:
        await create_admin_user(admin_email, admin_password, admin_name)
    except Exception as e:
        log_error(
            f"Error creating admin user: {str(e)}", "create_admin", {"error": str(e)}
        )
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
