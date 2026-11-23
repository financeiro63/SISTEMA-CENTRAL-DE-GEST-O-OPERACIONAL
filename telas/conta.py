"""Minha conta: troca de senha."""
import streamlit as st

import auth


def render():
    u = auth.usuario_atual()
    st.title("Minha conta")
    st.write(f"**{u['nome']}** · {auth.PERFIS[u['perfil']]}"
             + (f" · {u['local_nome']}" if u.get("local_nome") else ""))
    st.subheader("Trocar senha")
    auth.tela_trocar_senha()
