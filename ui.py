"""Componentes visuais e utilidades comuns."""
import re

import pandas as pd

import streamlit as st

import auth
import db

AZUL = "#0B4F9C"
AMARELO = "#F5C400"

UNIDADES_MEDIDA = ["un", "cx", "pct", "fd", "rl", "par", "kit", "l", "ml", "kg", "g", "m", "galão", "frasco"]

CSS = f"""
<style>
.block-container {{ padding-top: 1.6rem; }}
.login-titulo {{
    text-align:center; font-size:1.6rem; font-weight:700; color:{AZUL};
    margin: 3rem 0 1rem 0; border-bottom: 4px solid {AMARELO}; padding-bottom:.5rem;
}}
.card {{
    background:#FFFFFF; border:1px solid #DCE5F2; border-left:6px solid {AZUL};
    border-radius:10px; padding:.8rem 1rem; margin-bottom:.8rem; min-height:92px;
}}
.card.alerta {{ border-left-color:{AMARELO}; }}
.card.inativo {{ border-left-color:#C9D2DF; opacity:.65; }}
.card .rotulo {{ font-size:.82rem; color:#5B6B82; }}
.card .valor {{ font-size:1.6rem; font-weight:700; color:#1A2433; }}
.card .nota {{ font-size:.72rem; color:#8794A8; }}
</style>
"""


def aplicar_estilo():
    st.markdown(CSS, unsafe_allow_html=True)


def card(rotulo: str, valor, nota: str = "", tipo: str = ""):
    st.markdown(
        f"<div class='card {tipo}'><div class='rotulo'>{rotulo}</div>"
        f"<div class='valor'>{valor}</div><div class='nota'>{nota}</div></div>",
        unsafe_allow_html=True,
    )


def filtro_unidade(chave: str, incluir_central: bool = False):
    """Seletor 'Todas as unidades / unidade específica'.
    Gerente fica travado na própria unidade. Devolve (id ou None, nome)."""
    u = auth.usuario_atual()
    if u["perfil"] == "gerente":
        st.caption(f"Unidade: **{u['local_nome']}**")
        return u["local_id"], u["local_nome"]
    df = db.locais(incluir_central=incluir_central)
    opcoes = ["Todas as unidades"] + df["nome"].tolist()
    escolha = st.selectbox("Unidade", opcoes, key=chave)
    if escolha == "Todas as unidades":
        return None, escolha
    return int(df.loc[df["nome"] == escolha, "id"].iloc[0]), escolha


def somente_numeros(txt: str | None) -> str:
    return re.sub(r"\D", "", txt or "")


def cnpj_valido(cnpj: str) -> bool:
    c = somente_numeros(cnpj)
    if len(c) != 14 or c == c[0] * 14:
        return False
    def dv(base, pesos):
        s = sum(int(d) * p for d, p in zip(base, pesos))
        r = s % 11
        return "0" if r < 2 else str(11 - r)
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6] + p1
    d1 = dv(c[:12], p1)
    d2 = dv(c[:12] + d1, p2)
    return c[12:] == d1 + d2


def formatar_cnpj(cnpj: str | None) -> str:
    c = somente_numeros(cnpj)
    if len(c) != 14:
        return cnpj or ""
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def valor(registro, campo: str, padrao=None):
    """Lê um campo de um registro tratando vazio/NaN como 'padrao'."""
    if registro is None:
        return padrao
    v = registro[campo]
    try:
        if v is None or pd.isna(v):
            return padrao
    except (TypeError, ValueError):
        pass
    return v


def vazio_para_none(v):
    if v is None:
        return None
    if isinstance(v, str) and not v.strip():
        return None
    return v.strip() if isinstance(v, str) else v


def sem_permissao():
    st.error("Você não tem permissão para acessar esta página.")
    st.stop()
