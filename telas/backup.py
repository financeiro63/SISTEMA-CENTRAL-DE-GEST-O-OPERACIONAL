"""Exportação de backup completo em Excel (o plano gratuito do Supabase não faz backup)."""
import io
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import auth
import db
import ui

TABELAS = ["locais", "usuarios", "categorias", "fornecedores", "fornecedor_categorias",
           "produtos", "estoque_saldos", "log_acoes"]


def render():
    if not auth.tem_perfil("gestor"):
        ui.sem_permissao()
    st.title("Backup")
    st.info("O plano gratuito do banco **não faz backup automático**. "
            "Baixe este arquivo pelo menos **1 vez por semana** e guarde no Google Drive.")

    if st.button("Gerar backup agora", type="primary"):
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as xls:
            for t in TABELAS:
                df = db.query(f"select * from {t}")
                if t == "usuarios":
                    df = df.drop(columns=["senha_hash"])  # nunca exporta senhas
                for col in df.select_dtypes(include=["datetimetz"]).columns:
                    df[col] = df[col].dt.tz_convert("America/Sao_Paulo").dt.tz_localize(None)
                df.to_excel(xls, sheet_name=t[:31], index=False)
        agora = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d_%Hh%M")
        db.registrar("backup gerado")
        st.download_button("Baixar backup (.xlsx)", buffer.getvalue(),
                           file_name=f"backup_gestao_manta_{agora}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
