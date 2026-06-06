from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Callable

import customtkinter as ctk

from database.db_connection import DatabaseConnectionError, connection_scope
from widgets.sidebar import Sidebar


class ProfileRepository:
    """Database operations for the logged-in user's profile."""

    HASH_ITERATIONS = 260_000

    PROFILE_QUERY = """
        SELECT
            U.USER_ID,
            U.DEPARTMENT_ID,
            U.NAME,
            U.BATCH,
            U.EMAIL,
            U.PHONE,
            U.ROLE,
            U.STATUS,
            U.CREATED_AT,
            D.DEPARTMENT_NAME,
            D.FACULTY
        FROM USERS U
        JOIN DEPARTMENTS D
          ON U.DEPARTMENT_ID = D.DEPARTMENT_ID
        WHERE U.USER_ID = :user_id
    """

    def fetch_profile(self, user_id: int) -> dict:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(self.PROFILE_QUERY, {"user_id": user_id})
                row = cursor.fetchone()
            finally:
                cursor.close()

        if row is None:
            raise ValueError("Profile not found.")

        return {
            "user_id": row[0],
            "department_id": row[1],
            "name": row[2],
            "batch": row[3],
            "email": row[4],
            "phone": row[5],
            "role": row[6],
            "status": row[7],
            "created_at": row[8],
            "department_name": row[9],
            "faculty": row[10],
        }

    def update_phone(self, user_id: int, phone: str) -> dict:
        phone_value = phone.strip() or None

        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    UPDATE USERS
                    SET PHONE = :phone
                    WHERE USER_ID = :user_id
                    """,
                    {"phone": phone_value, "user_id": user_id},
                )
                if cursor.rowcount != 1:
                    raise ValueError("Profile not found.")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()

        return self.fetch_profile(user_id)

    def change_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
    ) -> None:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    SELECT PASSWORD_HASH
                    FROM USERS
                    WHERE USER_ID = :user_id
                    """,
                    {"user_id": user_id},
                )
                row = cursor.fetchone()
                if row is None:
                    raise ValueError("Profile not found.")

                if not self._verify_password(current_password, str(row[0] or "")):
                    raise ValueError("Current password is incorrect.")

                cursor.execute(
                    """
                    UPDATE USERS
                    SET PASSWORD_HASH = :password_hash
                    WHERE USER_ID = :user_id
                    """,
                    {
                        "password_hash": self._hash_password(new_password),
                        "user_id": user_id,
                    },
                )
                if cursor.rowcount != 1:
                    raise ValueError("Profile not found.")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()

    @classmethod
    def _hash_password(cls, password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            cls.HASH_ITERATIONS,
        ).hex()
        return f"pbkdf2_sha256${cls.HASH_ITERATIONS}${salt}${digest}"

    @staticmethod
    def _verify_password(password: str, stored_password: str) -> bool:
        if not stored_password:
            return False

        if hmac.compare_digest(password, stored_password):
            return True

        password_bytes = password.encode("utf-8")
        normalized = stored_password.strip()

        for algorithm in ("sha256", "sha512"):
            digest = hashlib.new(algorithm, password_bytes).hexdigest()
            if hmac.compare_digest(digest, normalized.lower()):
                return True

            prefixed = f"{algorithm}${digest}"
            if hmac.compare_digest(prefixed, normalized.lower()):
                return True

        parts = normalized.split("$")
        if len(parts) == 4 and parts[0].lower() == "pbkdf2_sha256":
            try:
                iterations = int(parts[1])
            except ValueError:
                return False

            derived = hashlib.pbkdf2_hmac(
                "sha256",
                password_bytes,
                parts[2].encode("utf-8"),
                iterations,
            ).hex()
            return hmac.compare_digest(derived, parts[3])

        return False


class ProfilePage(ctk.CTkFrame):
    """Logged-in user profile screen."""

    INFO_FIELDS = (
        ("name", "Name"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("department_name", "Department"),
        ("faculty", "Faculty"),
        ("batch", "Batch"),
        ("role", "Role"),
        ("status", "Status"),
    )

    def __init__(
        self,
        master: ctk.CTk,
        user: dict,
        on_navigate: Callable[[str], None],
        on_logout: Callable[[], None],
        on_user_updated: Callable[[dict], None],
    ) -> None:
        super().__init__(master, fg_color="#0b1018")
        self.user = user
        self.on_user_updated = on_user_updated
        self.repository = ProfileRepository()

        self.message_var = ctk.StringVar(value="")
        self.phone_var = ctk.StringVar(value=str(user.get("phone") or ""))
        self.current_password_var = ctk.StringVar()
        self.new_password_var = ctk.StringVar()
        self.confirm_password_var = ctk.StringVar()
        self.info_labels: dict[str, ctk.CTkLabel] = {}

        self._build_layout(on_navigate, on_logout)
        self.after(100, self.refresh)

    def _build_layout(
        self,
        on_navigate: Callable[[str], None],
        on_logout: Callable[[], None],
    ) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        sidebar = Sidebar(
            self,
            user=self.user,
            active_key="profile",
            on_select=on_navigate,
            on_logout=on_logout,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")

        self.content = ctk.CTkScrollableFrame(
            self,
            fg_color="#0b1018",
            scrollbar_button_color="#334155",
            scrollbar_button_hover_color="#475569",
        )
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_message_banner()
        self._build_profile_cards()
        self._build_forms()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(28, 18))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Profile",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Personal account information",
            font=ctk.CTkFont(size=14),
            text_color="#94a3b8",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.refresh_button = ctk.CTkButton(
            header,
            text="Refresh",
            command=self.refresh,
            width=116,
            height=38,
            corner_radius=8,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#e2e8f0",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.refresh_button.grid(row=0, column=1, rowspan=2, sticky="e")

    def _build_message_banner(self) -> None:
        self.message_banner = ctk.CTkLabel(
            self.content,
            textvariable=self.message_var,
            fg_color="#0f172a",
            text_color="#cbd5e1",
            corner_radius=8,
            height=38,
            font=ctk.CTkFont(size=13),
            wraplength=780,
            justify="left",
        )
        self.message_banner.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 16))
        self.message_banner.grid_remove()

    def _build_profile_cards(self) -> None:
        grid = ctk.CTkFrame(self.content, fg_color="transparent")
        grid.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 22))
        grid.grid_columnconfigure(0, weight=1, uniform="profile")
        grid.grid_columnconfigure(1, weight=1, uniform="profile")

        for index, (key, title) in enumerate(self.INFO_FIELDS):
            card = ctk.CTkFrame(grid, fg_color="#111827", corner_radius=8)
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=6, pady=6)
            card.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#94a3b8",
            ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 4))

            value = ctk.CTkLabel(
                card,
                text="--",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="#f8fafc",
                wraplength=360,
                justify="left",
            )
            value.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 16))
            self.info_labels[key] = value

    def _build_forms(self) -> None:
        forms = ctk.CTkFrame(self.content, fg_color="transparent")
        forms.grid(row=3, column=0, sticky="ew", padx=28, pady=(0, 28))
        forms.grid_columnconfigure(0, weight=1, uniform="forms")
        forms.grid_columnconfigure(1, weight=1, uniform="forms")

        self._build_phone_form(forms).grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self._build_password_form(forms).grid(row=0, column=1, sticky="nsew", padx=6, pady=6)

    def _build_phone_form(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        panel = ctk.CTkFrame(parent, fg_color="#111827", corner_radius=8)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel,
            text="Update Phone Number",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 14))

        self.phone_entry = ctk.CTkEntry(
            panel,
            textvariable=self.phone_var,
            placeholder_text="Phone number",
            height=42,
            border_width=1,
            border_color="#334155",
            fg_color="#0f172a",
            text_color="#f8fafc",
            placeholder_text_color="#64748b",
            corner_radius=8,
        )
        self.phone_entry.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 14))

        self.phone_button = ctk.CTkButton(
            panel,
            text="Save Phone",
            command=self.update_phone,
            height=42,
            corner_radius=8,
            fg_color="#14b8a6",
            hover_color="#0f766e",
            text_color="#042f2e",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.phone_button.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))

        return panel

    def _build_password_form(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        panel = ctk.CTkFrame(parent, fg_color="#111827", corner_radius=8)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel,
            text="Change Password",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 14))

        self.current_password_entry = self._password_entry(
            panel,
            row=1,
            variable=self.current_password_var,
            placeholder="Current password",
        )
        self.new_password_entry = self._password_entry(
            panel,
            row=2,
            variable=self.new_password_var,
            placeholder="New password",
        )
        self.confirm_password_entry = self._password_entry(
            panel,
            row=3,
            variable=self.confirm_password_var,
            placeholder="Confirm new password",
        )

        self.password_button = ctk.CTkButton(
            panel,
            text="Update Password",
            command=self.change_password,
            height=42,
            corner_radius=8,
            fg_color="#14b8a6",
            hover_color="#0f766e",
            text_color="#042f2e",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.password_button.grid(row=4, column=0, sticky="ew", padx=20, pady=(2, 20))

        return panel

    def _password_entry(
        self,
        parent: ctk.CTkFrame,
        row: int,
        variable: ctk.StringVar,
        placeholder: str,
    ) -> ctk.CTkEntry:
        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            placeholder_text=placeholder,
            show="*",
            height=42,
            border_width=1,
            border_color="#334155",
            fg_color="#0f172a",
            text_color="#f8fafc",
            placeholder_text_color="#64748b",
            corner_radius=8,
        )
        entry.grid(row=row, column=0, sticky="ew", padx=20, pady=(0, 12))
        return entry

    def refresh(self) -> None:
        self.refresh_button.configure(state="disabled", text="Loading...")
        self.update_idletasks()

        try:
            profile = self.repository.fetch_profile(int(self.user["user_id"]))
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Profile query failed: {exc}", "error")
        else:
            self._render_profile(profile)
        finally:
            self.refresh_button.configure(state="normal", text="Refresh")

    def update_phone(self) -> None:
        phone = self.phone_var.get().strip()
        if len(phone) > 20:
            self._show_message("Phone number cannot exceed 20 characters.", "error")
            return

        self.phone_button.configure(state="disabled", text="Saving...")
        self.update_idletasks()

        try:
            profile = self.repository.update_phone(int(self.user["user_id"]), phone)
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Phone update failed: {exc}", "error")
        else:
            self._render_profile(profile)
            self._show_message("Phone number updated successfully.", "success")
        finally:
            self.phone_button.configure(state="normal", text="Save Phone")

    def change_password(self) -> None:
        current_password = self.current_password_var.get()
        new_password = self.new_password_var.get()
        confirm_password = self.confirm_password_var.get()

        if not current_password or not new_password or not confirm_password:
            self._show_message("Enter current password, new password, and confirmation.", "error")
            return

        if new_password != confirm_password:
            self._show_message("New password and confirmation do not match.", "error")
            return

        if len(new_password) < 6:
            self._show_message("New password must be at least 6 characters.", "error")
            return

        self.password_button.configure(state="disabled", text="Updating...")
        self.update_idletasks()

        try:
            self.repository.change_password(
                int(self.user["user_id"]),
                current_password,
                new_password,
            )
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Password update failed: {exc}", "error")
        else:
            self.current_password_var.set("")
            self.new_password_var.set("")
            self.confirm_password_var.set("")
            self._show_message("Password updated successfully.", "success")
        finally:
            self.password_button.configure(state="normal", text="Update Password")

    def _render_profile(self, profile: dict) -> None:
        self.user.update(profile)
        self.on_user_updated(profile)
        self.phone_var.set(str(profile.get("phone") or ""))

        for key, label in self.info_labels.items():
            value = profile.get(key)
            if key in {"role", "status"} and value is not None:
                value = str(value).title()
            label.configure(text=str(value or "Not provided"))

    def _show_message(self, message: str, kind: str) -> None:
        colors = {
            "success": ("#064e3b", "#bbf7d0"),
            "error": ("#451a1a", "#fecaca"),
        }
        fg_color, text_color = colors.get(kind, ("#0f172a", "#cbd5e1"))
        self.message_banner.configure(fg_color=fg_color, text_color=text_color)
        self.message_var.set(message)
        self.message_banner.grid()
