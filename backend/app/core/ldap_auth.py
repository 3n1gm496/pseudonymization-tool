"""
Autenticazione LDAP per il Local Pseudonymization Tool — v5.2.0

Questo modulo gestisce il flusso di autenticazione tramite LDAP (eDirectory, Active Directory).
È distinto da ldap_detector.py, che si occupa dell'arricchimento dei dati per il rilevamento.

Flusso di autenticazione:
1. L'utente sceglie "Login Aziendale (LDAP)" nella UI.
2. Il backend riceve username e password.
3. Questo modulo cerca l'utente nel server LDAP tramite l'attributo `cn` di `inetOrgPerson`.
4. Se trovato, esegue un bind LDAP con il DN dell'utente e la password fornita.
5. Se il bind ha successo, verifica l'appartenenza ai gruppi configurati per mappare il ruolo.
6. Ritorna il ruolo ('admin' o 'operator') o None se l'autenticazione fallisce.

Sicurezza:
- La password dell'utente non viene mai loggata.
- In caso di irraggiungibilità del server LDAP, il modulo ritorna None (fail-safe).
- Compatibile con eDirectory (Novell/NetIQ) tramite ldap3.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _get_ldap3():
    """Import ldap3 con gestione graceful se non installato."""
    try:
        import ldap3

        return ldap3
    except ImportError:
        return None


def authenticate_ldap(username: str, password: str) -> Optional[str]:
    """
    Autentica un utente tramite LDAP.

    Esegue la ricerca dell'utente per attributo `cn` nell'objectClass `inetOrgPerson`,
    poi esegue un bind con le credenziali fornite per verificare la password.
    Infine, determina il ruolo in base all'appartenenza ai gruppi configurati.

    Args:
        username: Il nome utente (verrà cercato come `cn`).
        password: La password in chiaro dell'utente.

    Returns:
        Il ruolo ('admin' o 'operator') se l'autenticazione ha successo, None altrimenti.
    """
    ldap3 = _get_ldap3()
    if ldap3 is None:
        logger.warning("ldap_auth: libreria ldap3 non installata, autenticazione LDAP non disponibile.")
        return None

    config = _get_ldap_auth_config()
    if config is None or not config.auth_enabled:
        logger.debug("ldap_auth: autenticazione LDAP non abilitata nella configurazione.")
        return None

    if not username or not password:
        return None

    service_conn = None
    try:
        # Step 1: Connessione con le credenziali di servizio (bind DN) per la ricerca
        server = _build_server(ldap3, config)
        service_conn = _bind_service(ldap3, server, config)
        if service_conn is None:
            logger.warning("ldap_auth: impossibile connettersi al server LDAP con le credenziali di servizio.")
            return None

        # Step 2: Ricerca del DN dell'utente tramite attributo `cn`
        user_dn = _search_user_dn(ldap3, service_conn, config, username)
        if user_dn is None:
            logger.info("ldap_auth: utente '%s' non trovato nel server LDAP.", username)
            return None

        # Step 3: Bind con le credenziali dell'utente per verificare la password
        if not _bind_as_user(ldap3, server, user_dn, password):
            logger.info("ldap_auth: password errata per l'utente '%s'.", username)
            return None

        # Step 4: Determinazione del ruolo tramite appartenenza ai gruppi
        role = _get_role_from_groups(ldap3, service_conn, config, user_dn)
        logger.info("ldap_auth: autenticazione riuscita per '%s', ruolo: %s.", username, role)
        return role

    except Exception as exc:
        # Qualsiasi errore di connessione o LDAP viene gestito qui.
        # Non si propaga l'eccezione per garantire il fallback all'autenticazione locale.
        logger.warning("ldap_auth: errore durante l'autenticazione LDAP per '%s': %s", username, type(exc).__name__)
        return None
    finally:
        # Chiudi sempre la connessione di servizio per evitare leak
        if service_conn is not None:
            try:
                service_conn.unbind()
            except Exception:
                pass


def is_ldap_auth_available() -> bool:
    """
    Verifica se l'autenticazione LDAP è abilitata e configurata.
    Usato dal frontend per mostrare/nascondere l'opzione di login LDAP.
    """
    config = _get_ldap_auth_config()
    return config is not None and config.auth_enabled and bool(config.host) and bool(config.auth_user_base_dn)


# ─── Funzioni private ─────────────────────────────────────────────────────────


def _get_ldap_auth_config():
    """Recupera la configurazione LDAP attuale dal detector (fonte unica di verità)."""
    try:
        from app.detectors.ldap_detector import get_ldap_config

        return get_ldap_config()
    except Exception as exc:
        logger.warning("ldap_auth: impossibile recuperare la configurazione LDAP: %s", exc)
        return None


def _build_server(ldap3, config):
    """Costruisce l'oggetto Server ldap3 in base alla configurazione."""
    tls = None
    use_ssl = getattr(config, "use_ssl", False) or getattr(config, "use_tls", False)
    needs_tls = use_ssl or getattr(config, "starttls", False)
    if needs_tls:
        validate_cert = getattr(config, "tls_validate_cert", False)
        tls = ldap3.Tls(validate=ldap3.ssl.CERT_REQUIRED if validate_cert else ldap3.ssl.CERT_NONE)
    return ldap3.Server(
        config.host,
        port=config.port,
        use_ssl=use_ssl,
        tls=tls,
        connect_timeout=5,
        get_info=ldap3.NONE,  # Non richiedere info server per sicurezza e performance
    )


def _bind_service(ldap3, server, config):
    """
    Esegue il bind con le credenziali di servizio per la ricerca degli utenti.
    Ritorna la connessione se il bind ha successo, None altrimenti.
    """
    if not config.bind_dn or not config.bind_password:
        logger.warning("ldap_auth: bind_dn o bind_password non configurati per la ricerca utenti.")
        return None
    try:
        use_ssl = getattr(config, "use_ssl", False) or getattr(config, "use_tls", False)
        use_starttls = getattr(config, "starttls", False) and not use_ssl
        if use_starttls:
            # STARTTLS: connetti senza auto_bind, poi start_tls, poi bind manuale
            conn = ldap3.Connection(
                server,
                user=config.bind_dn,
                password=config.bind_password,
                auto_bind=ldap3.AUTO_BIND_NONE,
                raise_exceptions=True,
            )
            conn.open()
            conn.start_tls()
            if not conn.bind():
                conn.unbind()
                return None
        else:
            # SSL o plaintext: usa auto_bind per semplicità
            conn = ldap3.Connection(
                server,
                user=config.bind_dn,
                password=config.bind_password,
                auto_bind=ldap3.AUTO_BIND_NO_TLS,
                raise_exceptions=True,
            )
        return conn
    except Exception as exc:
        logger.warning("ldap_auth: bind di servizio fallito: %s", type(exc).__name__)
        return None


def _search_user_dn(ldap3, conn, config, username: str) -> Optional[str]:
    """
    Cerca il DN dell'utente nel server LDAP tramite l'attributo `cn` di `inetOrgPerson`.
    Questo è il metodo corretto per eDirectory.

    Args:
        conn: Connessione LDAP attiva con credenziali di servizio.
        config: Configurazione LDAP.
        username: Il valore del `cn` da cercare.

    Returns:
        Il DN completo dell'utente se trovato, None altrimenti.
    """
    search_base = config.auth_user_base_dn or config.base_dn
    # Filtro specifico per eDirectory: cerca per cn nell'objectClass inetOrgPerson
    search_filter = f"(&(objectClass=inetOrgPerson)(cn={ldap3.utils.conv.escape_filter_chars(username)}))"
    try:
        conn.search(
            search_base=search_base,
            search_filter=search_filter,
            search_scope=ldap3.SUBTREE,
            attributes=["dn"],
            size_limit=2,  # Ci aspettiamo al massimo 1 risultato; 2 per rilevare duplicati
        )
        entries = conn.entries
        if not entries:
            return None
        if len(entries) > 1:
            logger.warning(
                "ldap_auth: trovati %d utenti con cn='%s', atteso 1. Autenticazione negata.", len(entries), username
            )
            return None
        return entries[0].entry_dn
    except Exception as exc:
        logger.warning("ldap_auth: ricerca utente fallita: %s", type(exc).__name__)
        return None


def _bind_as_user(ldap3, server, user_dn: str, password: str) -> bool:
    """
    Esegue un bind LDAP con il DN e la password dell'utente per verificare le credenziali.
    Questo è il meccanismo standard per verificare una password LDAP.

    Returns:
        True se il bind ha successo (password corretta), False altrimenti.
    """
    try:
        conn = ldap3.Connection(
            server,
            user=user_dn,
            password=password,
            raise_exceptions=False,  # Non sollevare eccezioni per bind falliti (password errata)
        )
        result = conn.bind()
        conn.unbind()
        return result
    except Exception as exc:
        logger.warning("ldap_auth: bind utente fallito per DN '%s': %s", user_dn[:30], type(exc).__name__)
        return False


def _get_role_from_groups(ldap3, conn, config, user_dn: str) -> str:
    """
    Determina il ruolo dell'utente verificando la sua appartenenza ai gruppi LDAP configurati.

    Logica di priorità:
    1. Se l'utente appartiene al gruppo admin → ruolo 'admin'
    2. Se l'utente appartiene al gruppo operator → ruolo 'operator'
    3. Se nessun gruppo corrisponde → ruolo di default dalla configurazione

    Args:
        conn: Connessione LDAP attiva con credenziali di servizio.
        config: Configurazione LDAP con i DN dei gruppi.
        user_dn: Il DN dell'utente autenticato.

    Returns:
        Il ruolo ('admin', 'operator') come stringa.
    """
    default_role = config.auth_default_role or "operator"

    # Se nessun gruppo è configurato, assegna il ruolo di default
    if not config.auth_admin_group_dn and not config.auth_operator_group_dn:
        logger.debug("ldap_auth: nessun gruppo configurato, assegno ruolo di default: %s", default_role)
        return default_role

    # Verifica appartenenza al gruppo admin (priorità massima)
    if config.auth_admin_group_dn and _is_member_of(ldap3, conn, user_dn, config.auth_admin_group_dn):
        return "admin"

    # Verifica appartenenza al gruppo operator
    if config.auth_operator_group_dn and _is_member_of(ldap3, conn, user_dn, config.auth_operator_group_dn):
        return "operator"

    logger.debug(
        "ldap_auth: utente '%s' non appartiene a nessun gruppo configurato, assegno ruolo di default: %s",
        user_dn[:30],
        default_role,
    )
    return default_role


def _is_member_of(ldap3, conn, user_dn: str, group_dn: str) -> bool:
    """
    Verifica se un utente è membro di un gruppo LDAP.

    Usa una ricerca sul gruppo con filtro `member` per compatibilità con
    eDirectory (che usa `member` o `uniqueMember`) e Active Directory.

    Args:
        conn: Connessione LDAP attiva.
        user_dn: Il DN dell'utente.
        group_dn: Il DN del gruppo da verificare.

    Returns:
        True se l'utente è membro del gruppo, False altrimenti.
    """
    try:
        # Cerca il gruppo e verifica se il DN dell'utente è nei suoi membri
        # Supporta sia `member` (RFC 2256) che `uniqueMember` (eDirectory)
        escaped_user_dn = ldap3.utils.conv.escape_filter_chars(user_dn)
        search_filter = f"(|(member={escaped_user_dn})(uniqueMember={escaped_user_dn}))"
        conn.search(
            search_base=group_dn,
            search_filter=search_filter,
            search_scope=ldap3.BASE,  # Cerca solo il gruppo specifico, non i sottogruppi
            attributes=["dn"],
            size_limit=1,
        )
        return len(conn.entries) > 0
    except Exception as exc:
        logger.warning("ldap_auth: verifica gruppo '%s' fallita: %s", group_dn[:40], type(exc).__name__)
        return False
