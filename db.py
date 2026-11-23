"""Conexão com o banco (Supabase / PostgreSQL) e funções de acesso."""
from contextlib import contextmanager

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


@st.cache_resource(show_spinner=False)
def get_engine():
    cfg = st.secrets["database"]
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=cfg["user"],
        password=cfg["password"],
        host=cfg["host"],
        port=int(cfg.get("port", 5432)),
        database=cfg.get("dbname", "postgres"),
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        pool_recycle=300,
        connect_args={"sslmode": "require"},
    )


def query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Executa um SELECT e devolve um DataFrame."""
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def query_one(sql: str, params: dict | None = None):
    """Executa um SELECT e devolve a primeira linha (ou None)."""
    with get_engine().connect() as conn:
        return conn.execute(text(sql), params or {}).mappings().first()


def execute(sql: str, params: dict | None = None):
    """Executa INSERT/UPDATE/DELETE em uma transação.
    Se o SQL tiver RETURNING, devolve a primeira linha."""
    with get_engine().begin() as conn:
        res = conn.execute(text(sql), params or {})
        if res.returns_rows:
            return res.mappings().first()
    return None


@contextmanager
def transacao():
    """Agrupa vários comandos: ou grava tudo, ou não grava nada."""
    with get_engine().begin() as conn:
        yield conn


def registrar(acao: str, tabela: str | None = None, registro_id: int | None = None,
              detalhe: str | None = None):
    """Grava no log de auditoria quem fez o quê."""
    usuario = st.session_state.get("usuario")
    try:
        execute(
            """insert into log_acoes (usuario_id, acao, tabela, registro_id, detalhe)
               values (:u, :a, :t, :r, :d)""",
            {"u": usuario["id"] if usuario else None, "a": acao, "t": tabela,
             "r": registro_id, "d": detalhe},
        )
    except Exception:
        pass  # o log nunca pode impedir a operação principal


# ---------------------------------------------------------------------
# Listas usadas em vários módulos
# ---------------------------------------------------------------------
def locais(somente_ativos: bool = True, incluir_central: bool = True) -> pd.DataFrame:
    sql = "select id, nome, tipo, recebe_via_central, ativo from locais where 1=1"
    if somente_ativos:
        sql += " and ativo"
    if not incluir_central:
        sql += " and tipo = 'unidade'"
    return query(sql + " order by tipo desc, nome")


def categorias(somente_ativas: bool = True) -> pd.DataFrame:
    sql = "select id, nome, ativo from categorias"
    if somente_ativas:
        sql += " where ativo"
    return query(sql + " order by nome")


def fornecedores_lista() -> pd.DataFrame:
    return query(
        """select id, coalesce(nullif(nome_fantasia, ''), razao_social) as nome
           from fornecedores where ativo order by 2"""
    )
