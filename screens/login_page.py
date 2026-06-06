from __future__ import annotations

import hashlib
import hmac
from typing import Callable

import customtkinter as ctk

from database.db_connection import DatabaseConnectionError, connection_scope


class AuthenticationError(RuntimeError):
    """Raised when supplied login credentials are not valid."""


class InactiveAccountError(AuthenticationError):
    """Raised when a user exists but is not allowed to sign in."""


class AuthRepository:
    """Database access for authenticating SkillSwap users."""

    USER_QUERY = """
        SELECT
            U.USER_ID,
            U.DEPARTMENT_ID,
            U.NAME,
            U.BATCH,
            U.EMAIL,
            U.PHONE,
            U.PASSWORD_HASH,
            U.ROLE,
            U.STATUS,
            U.CREATED_AT,
            D.DEPARTMENT_NAME,
            D.FACULTY
        FROM USERS U
        JOIN DEPARTMENTS D
          ON D.DEPARTMENT_ID = U.DEPARTMENT_ID
        WHERE LOWER(U.EMAIL) = LOWER(:email)
    """

    def authenticate(self, email: str, password: str) -> dict:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(self.USER_QUERY, {"email": email.strip()})
                row = cursor.fetchone()
            finally:
                cursor.close()

        if row is None:
            raise AuthenticationError("Invalid email or password.")

        stored_password = str(row[6] or "")
        if not self._verify_password(password, stored_password):
            raise AuthenticationError("Invalid email or password.")

        if str(row[8]).upper() != "ACTIVE":
            raise InactiveAccountError("This account is inactive.")

        return {
            "user_id": row[0],
            "department_id": row[1],
            "name": row[2],
            "batch": row[3],
            "email": row[4],
            "phone": row[5],
            "role": row[7],
            "status": row[8],
            "created_at": row[9],
            "department_name": row[10],
            "faculty": row[11],
        }

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

            salt = parts[2].encode("utf-8")
            expected = parts[3]
            derived = hashlib.pbkdf2_hmac(
                "sha256",
                password_bytes,
                salt,
                iterations,
            ).hex()
            return hmac.compare_digest(derived, expected)

        return False


class LoginPage(ctk.CTkFrame):
    """First screen shown by the app."""

    def __init__(
        self,
        master: ctk.CTk,
        on_login_success: Callable[[dict], None],
    ) -> None:
        super().__init__(master, fg_color="#0b1018")
        self.on_login_success = on_login_success
        self.auth_repository = AuthRepository()

        self.email_var = ctk.StringVar()
        self.password_var = ctk.StringVar()
        self.show_password_var = ctk.BooleanVar(value=False)
        self.status_var = ctk.StringVar(value="")

        self._is_busy = False
        self._build_layout()

    def _build_layout(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.grid(row=0, column=0, sticky="nsew", padx=36, pady=36)
        shell.grid_columnconfigure(0, weight=1, minsize=360)
        shell.grid_columnconfigure(1, weight=1, minsize=420)
        shell.grid_rowconfigure(0, weight=1)

        brand_panel = ctk.CTkFrame(shell, fg_color="#111827", corner_radius=8)
        brand_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        brand_panel.grid_columnconfigure(0, weight=1)
        brand_panel.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            brand_panel,
            text="SkillSwap",
            font=ctk.CTkFont(size=34, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w", padx=34, pady=(42, 10))

        ctk.CTkLabel(
            brand_panel,
            text="University peer learning",
            font=ctk.CTkFont(size=17),
            text_color="#94a3b8",
        ).grid(row=1, column=0, sticky="w", padx=34)

        ctk.CTkFrame(
            brand_panel,
            fg_color="#14b8a6",
            width=88,
            height=4,
            corner_radius=2,
        ).grid(row=2, column=0, sticky="w", padx=34, pady=(26, 0))

        info = ctk.CTkFrame(brand_panel, fg_color="#0f172a", corner_radius=8)
        info.grid(row=4, column=0, sticky="ew", padx=28, pady=28)
        info.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            info,
            text="Oracle-backed desktop workspace",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#e2e8f0",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 6))

        ctk.CTkLabel(
            info,
            text="Sign in with an active USERS record.",
            font=ctk.CTkFont(size=13),
            text_color="#94a3b8",
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 18))

        form_outer = ctk.CTkFrame(shell, fg_color="transparent")
        form_outer.grid(row=0, column=1, sticky="nsew")
        form_outer.grid_rowconfigure(0, weight=1)
        form_outer.grid_columnconfigure(0, weight=1)

        form = ctk.CTkFrame(form_outer, fg_color="#111827", corner_radius=8)
        form.grid(row=0, column=0, sticky="nsew", padx=(18, 0), pady=20)
        form.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            form,
            text="Sign In",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w", padx=34, pady=(42, 8))

        ctk.CTkLabel(
            form,
            text="Use your SkillSwap email and password.",
            font=ctk.CTkFont(size=14),
            text_color="#94a3b8",
        ).grid(row=1, column=0, sticky="w", padx=34, pady=(0, 26))

        self.email_entry = self._create_entry(
            form,
            row=2,
            label="Email",
            variable=self.email_var,
            placeholder="name@skillswap.edu",
        )

        self.password_entry = self._create_entry(
            form,
            row=3,
            label="Password",
            variable=self.password_var,
            placeholder="Password",
            show="*",
        )

        show_password = ctk.CTkCheckBox(
            form,
            text="Show password",
            variable=self.show_password_var,
            command=self._toggle_password_visibility,
            fg_color="#14b8a6",
            hover_color="#0f766e",
            border_color="#475569",
            text_color="#cbd5e1",
            font=ctk.CTkFont(size=13),
        )
        show_password.grid(row=4, column=0, sticky="w", padx=34, pady=(6, 16))

        self.status_label = ctk.CTkLabel(
            form,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=13),
            text_color="#f87171",
            wraplength=360,
            justify="left",
        )
        self.status_label.grid(row=5, column=0, sticky="ew", padx=34, pady=(0, 12))

        self.login_button = ctk.CTkButton(
            form,
            text="Sign In",
            command=self._submit,
            height=46,
            corner_radius=8,
            fg_color="#14b8a6",
            hover_color="#0f766e",
            text_color="#04111d",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.login_button.grid(row=6, column=0, sticky="ew", padx=34, pady=(0, 34))

        self.email_entry.focus_set()
        self.email_entry.bind("<Return>", self._submit_from_event)
        self.password_entry.bind("<Return>", self._submit_from_event)

    def _create_entry(
        self,
        parent: ctk.CTkFrame,
        row: int,
        label: str,
        variable: ctk.StringVar,
        placeholder: str,
        show: str | None = None,
    ) -> ctk.CTkEntry:
        wrapper = ctk.CTkFrame(parent, fg_color="transparent")
        wrapper.grid(row=row, column=0, sticky="ew", padx=34, pady=(0, 16))
        wrapper.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            wrapper,
            text=label,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#cbd5e1",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        entry = ctk.CTkEntry(
            wrapper,
            textvariable=variable,
            placeholder_text=placeholder,
            show=show,
            height=44,
            border_width=1,
            border_color="#334155",
            fg_color="#0f172a",
            text_color="#f8fafc",
            placeholder_text_color="#64748b",
            corner_radius=8,
        )
        entry.grid(row=1, column=0, sticky="ew")
        return entry

    def _toggle_password_visibility(self) -> None:
        self.password_entry.configure(show="" if self.show_password_var.get() else "*")

    def _submit_from_event(self, _event) -> None:
        self._submit()

    def _submit(self) -> None:
        if self._is_busy:
            return

        email = self.email_var.get().strip()
        password = self.password_var.get()

        if not email or not password:
            self.status_var.set("Enter both email and password.")
            return

        self._set_busy(True)
        self.status_var.set("")
        self.update_idletasks()

        try:
            user = self.auth_repository.authenticate(email, password)
        except InactiveAccountError as exc:
            self.status_var.set(str(exc))
            self._set_busy(False)
        except AuthenticationError as exc:
            self.status_var.set(str(exc))
            self._set_busy(False)
        except DatabaseConnectionError as exc:
            self.status_var.set(str(exc))
            self._set_busy(False)
        except Exception as exc:
            self.status_var.set(f"Login failed: {exc}")
            self._set_busy(False)
        else:
            self.on_login_success(user)

    def _set_busy(self, is_busy: bool) -> None:
        self._is_busy = is_busy
        state = "disabled" if is_busy else "normal"
        button_text = "Signing In..." if is_busy else "Sign In"
        self.login_button.configure(state=state, text=button_text)
        self.email_entry.configure(state=state)
        self.password_entry.configure(state=state)
