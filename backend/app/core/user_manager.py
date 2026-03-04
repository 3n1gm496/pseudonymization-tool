"""
Gestione utenti locali con SQLite e bcrypt.

Fornisce:
- Bootstrap automatico dell'utente admin al primo avvio
- CRUD utenti (create, read, update, delete)
- Verifica credenziali con bcrypt
- Ruoli: admin (accesso completo) e operator (solo scan/apply/download)

Il database SQLite è in STATE_DIR/users.db per persistenza tra riavvii.
"""

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional

import bcrypt

logger = logging.getLogger(__name__)

# Bcrypt cost factor — 12 è un buon compromesso sicurezza/velocità
_BCRYPT_ROUNDS = 12

# Ruoli validi
VALID_ROLES = {"admin", "operator"}
ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"

# Default admin bootstrap (solo se non esiste nessun utente)
DEFAULT_ADMIN_USERNAME = os.environ.get("AUTH_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("AUTH_PASSWORD", "")

_db_lock = threading.Lock()
_db_path: Optional[Path] = None


def _hash_password(password: str) -> str:
    """Genera un hash bcrypt della password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def _check_password(password: str, hashed: str) -> bool:
    """Verifica una password contro il suo hash bcrypt."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _dummy_verify() -> None:
    """
    Esegue un hash fittizio per prevenire timing attacks
    quando l'utente non esiste nel database.
    """
    bcrypt.checkpw(b"dummy", bcrypt.hashpw(b"dummy", bcrypt.gensalt(rounds=4)))


def _get_db_path() -> Path:
    """Ritorna il path del database SQLite degli utenti."""
    global _db_path
    if _db_path is None:
        state_dir = os.environ.get("PSEUDONYMIZER_STATE_DIR")
        if state_dir:
            _db_path = Path(state_dir) / "users.db"
        else:
            import tempfile

            _db_path = Path(tempfile.gettempdir()) / "pseudonymizer_batches" / "state" / "users.db"
        _db_path.parent.mkdir(parents=True, exist_ok=True)
    return _db_path


@contextmanager
def _get_conn():
    """Context manager per connessione SQLite thread-safe."""
    conn = sqlite3.connect(str(_get_db_path()), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_db() -> None:
    """Crea la tabella users se non esiste."""
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username    TEXT PRIMARY KEY NOT NULL,
                password_hash TEXT NOT NULL,
                role        TEXT NOT NULL DEFAULT 'operator',
                created_at  TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
                updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
                is_active   INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)
            """
        )
    logger.info("user_manager: database initialized at %s", _get_db_path())


def _bootstrap_admin() -> None:
    """
    Crea l'utente admin di default al primo avvio se non esiste nessun utente.
    Se AUTH_PASSWORD non è configurata, usa una password casuale sicura e la logga
    una sola volta (deve essere cambiata subito dall'operatore).
    """
    with _db_lock:
        with _get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if count > 0:
                return  # Utenti già presenti, nessun bootstrap necessario

        # Nessun utente: crea admin di default
        import secrets as _secrets

        password = DEFAULT_ADMIN_PASSWORD
        generated = False
        if not password:
            password = _secrets.token_urlsafe(16)
            generated = True

        _create_user_internal(DEFAULT_ADMIN_USERNAME, password, ROLE_ADMIN)

        if generated:
            logger.warning(
                "user_manager: ⚠️  BOOTSTRAP — admin creato con password generata: '%s' "
                "— CAMBIARE IMMEDIATAMENTE tramite il pannello utenti",
                password,
            )
        else:
            logger.info(
                "user_manager: bootstrap — admin '%s' creato con password da AUTH_PASSWORD",
                DEFAULT_ADMIN_USERNAME,
            )


def initialize() -> None:
    """
    Inizializza il database e fa il bootstrap dell'admin se necessario.
    Deve essere chiamato all'avvio dell'applicazione (lifespan).
    """
    _init_db()
    _bootstrap_admin()


# ─── CRUD ────────────────────────────────────────────────────────────────────


def _create_user_internal(username: str, password: str, role: str) -> None:
    """Crea un utente senza lock esterno (usato internamente)."""
    if role not in VALID_ROLES:
        raise ValueError(f"Ruolo non valido: {role}. Validi: {VALID_ROLES}")
    password_hash = _hash_password(password)
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, ?)
            """,
            (username, password_hash, role),
        )
    logger.info("user_manager: utente '%s' creato con ruolo '%s'", username, role)


def create_user(username: str, password: str, role: str = ROLE_OPERATOR) -> None:
    """
    Crea un nuovo utente locale.

    Args:
        username: Nome utente (univoco)
        password: Password in chiaro (verrà hashata con bcrypt)
        role: 'admin' o 'operator' (default: 'operator')

    Raises:
        ValueError: Se il ruolo non è valido o l'utente esiste già
    """
    if not username or not username.strip():
        raise ValueError("Il nome utente non può essere vuoto")
    if not password or len(password) < 8:
        raise ValueError("La password deve essere di almeno 8 caratteri")
    if role not in VALID_ROLES:
        raise ValueError(f"Ruolo non valido: {role}. Validi: {VALID_ROLES}")

    username = username.strip().lower()

    with _db_lock:
        # Verifica che l'utente non esista già
        with _get_conn() as conn:
            existing = conn.execute("SELECT username FROM users WHERE username = ?", (username,)).fetchone()
            if existing:
                raise ValueError(f"L'utente '{username}' esiste già")

        _create_user_internal(username, password, role)


def get_user(username: str) -> Optional[dict]:
    """
    Recupera un utente per username.

    Returns:
        Dict con username, role, created_at, updated_at, is_active
        oppure None se non trovato.
    """
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT username, role, created_at, updated_at, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)


def list_users() -> List[dict]:
    """
    Ritorna la lista di tutti gli utenti (senza password hash).

    Returns:
        Lista di dict con username, role, created_at, updated_at, is_active
    """
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT username, role, created_at, updated_at, is_active FROM users ORDER BY username"
        ).fetchall()
        return [dict(row) for row in rows]


def update_user_role(username: str, new_role: str) -> None:
    """
    Aggiorna il ruolo di un utente.

    Args:
        username: Nome utente
        new_role: Nuovo ruolo ('admin' o 'operator')

    Raises:
        ValueError: Se il ruolo non è valido o l'utente non esiste
    """
    if new_role not in VALID_ROLES:
        raise ValueError(f"Ruolo non valido: {new_role}. Validi: {VALID_ROLES}")

    with _db_lock:
        with _get_conn() as conn:
            result = conn.execute(
                """
                UPDATE users
                SET role = ?, updated_at = datetime('now', 'utc')
                WHERE username = ?
                """,
                (new_role, username),
            )
            if result.rowcount == 0:
                raise ValueError(f"Utente '{username}' non trovato")
    logger.info("user_manager: ruolo di '%s' aggiornato a '%s'", username, new_role)


def update_user_password(username: str, new_password: str) -> None:
    """
    Aggiorna la password di un utente.

    Args:
        username: Nome utente
        new_password: Nuova password in chiaro (min 8 caratteri)

    Raises:
        ValueError: Se la password è troppo corta o l'utente non esiste
    """
    if not new_password or len(new_password) < 8:
        raise ValueError("La password deve essere di almeno 8 caratteri")

    new_hash = _hash_password(new_password)

    with _db_lock:
        with _get_conn() as conn:
            result = conn.execute(
                """
                UPDATE users
                SET password_hash = ?, updated_at = datetime('now', 'utc')
                WHERE username = ?
                """,
                (new_hash, username),
            )
            if result.rowcount == 0:
                raise ValueError(f"Utente '{username}' non trovato")
    logger.info("user_manager: password di '%s' aggiornata", username)


def delete_user(username: str) -> None:
    """
    Elimina un utente.

    Args:
        username: Nome utente da eliminare

    Raises:
        ValueError: Se l'utente non esiste o è l'ultimo admin
    """
    with _db_lock:
        with _get_conn() as conn:
            # Verifica che l'utente esista
            user = conn.execute("SELECT role FROM users WHERE username = ?", (username,)).fetchone()
            if user is None:
                raise ValueError(f"Utente '{username}' non trovato")

            # Impedisce l'eliminazione dell'ultimo admin
            if user["role"] == ROLE_ADMIN:
                admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
                if admin_count <= 1:
                    raise ValueError(
                        "Impossibile eliminare l'ultimo utente admin. " "Crea un altro admin prima di eliminare questo."
                    )

            conn.execute("DELETE FROM users WHERE username = ?", (username,))
    logger.info("user_manager: utente '%s' eliminato", username)


def verify_credentials(username: str, password: str) -> Optional[str]:
    """
    Verifica le credenziali di un utente.

    Args:
        username: Nome utente
        password: Password in chiaro

    Returns:
        Il ruolo dell'utente ('admin' o 'operator') se le credenziali sono valide,
        None altrimenti.
    """
    if not username or not password:
        return None

    username = username.strip().lower()

    with _get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash, role, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    if row is None:
        # Esegui un hash fittizio per prevenire timing attacks
        _dummy_verify()
        return None

    if not row["is_active"]:
        _dummy_verify()
        return None

    if not _check_password(password, row["password_hash"]):
        return None

    return row["role"]


def get_user_role(username: str) -> Optional[str]:
    """
    Ritorna il ruolo di un utente, o None se non esiste.
    """
    with _get_conn() as conn:
        row = conn.execute("SELECT role FROM users WHERE username = ? AND is_active = 1", (username,)).fetchone()
        if row is None:
            return None
        return row["role"]


def count_admins() -> int:
    """Ritorna il numero di utenti admin attivi."""
    with _get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1").fetchone()[0]
