"""Notas Fiscais: consulta, lançamento manual e conferência."""
import io
from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy.exc import IntegrityError

import auth
import db
import ui

MESES = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _carregar(unidade_id: int | None) -> pd.DataFrame:
    filtro = "" if unidade_id is None else "where n.unidade_id = :u"
    df = db.query(
        f"""select n.id, n.data_emissao, l.nome as unidade, n.unidade_id,
                   coalesce(nullif(f.nome_fantasia, ''), f.razao_social) as fornecedor,
                   f.cnpj, n.numero, n.tipo, n.valor_total, n.conferir, n.observacao,
                   n.forma_pagamento, n.arquivo_url, n.origem
            from nfe n
            join locais l on l.id = n.unidade_id
            join fornecedores f on f.id = n.fornecedor_id
            {filtro}
            order by n.data_emissao desc, l.nome""",
        {"u": unidade_id},
    )
    if not df.empty:
        df["data_emissao"] = pd.to_datetime(df["data_emissao"])
        df["mes"] = df["data_emissao"].dt.strftime("%Y-%m")
        df["valor_total"] = df["valor_total"].astype(float)
    return df


def _rotulo_mes(m: str) -> str:
    ano, mes = m.split("-")
    return f"{MESES[int(mes)]}/{ano}"


def _excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    saida = df[["data_emissao", "unidade", "fornecedor", "numero", "tipo", "valor_total",
                "conferir", "observacao"]].copy()
    saida["data_emissao"] = saida["data_emissao"].dt.date
    saida.columns = ["Data", "Unidade", "Fornecedor", "NF", "Tipo", "Valor", "Conferir", "Observação"]
    with pd.ExcelWriter(buf, engine="openpyxl") as xls:
        saida.to_excel(xls, sheet_name="NFs", index=False)
    return buf.getvalue()


def render():
    st.title("Notas Fiscais")
    pode_editar = auth.tem_perfil("gestor", "compras")

    c1, c2 = st.columns([2, 3])
    with c1:
        unidade_id, unidade_nome = ui.filtro_unidade("nf_unidade")
    df = _carregar(unidade_id)

    if df.empty:
        st.info("Nenhuma NF lançada ainda.")
    else:
        # ---- Filtros ---------------------------------------------------
        meses = sorted(df["mes"].unique(), reverse=True)
        f1, f2, f3, f4 = st.columns([3, 3, 2, 2])
        with f1:
            sel_meses = st.multiselect("Mês de emissão", meses, default=meses[:1],
                                       format_func=_rotulo_mes, key="nf_meses",
                                       placeholder="Todos os meses")
        with f2:
            sel_forn = st.multiselect("Fornecedor", sorted(df["fornecedor"].unique()),
                                      key="nf_forn", placeholder="Todos")
        with f3:
            tipo = st.selectbox("Tipo", ["Todos", "Produto", "Serviço"], key="nf_tipo")
        with f4:
            so_conferir = st.checkbox("Só a conferir", key="nf_conf")
        busca = st.text_input("Buscar número da NF", key="nf_busca")

        vis = df.copy()
        if sel_meses:
            vis = vis[vis["mes"].isin(sel_meses)]
        if sel_forn:
            vis = vis[vis["fornecedor"].isin(sel_forn)]
        if tipo != "Todos":
            vis = vis[vis["tipo"] == ("produto" if tipo == "Produto" else "servico")]
        if so_conferir:
            vis = vis[vis["conferir"]]
        if busca.strip():
            vis = vis[vis["numero"].str.contains(busca.strip(), regex=False)]

        # ---- Indicadores ---------------------------------------------
        total = vis["valor_total"].sum()
        prod = vis.loc[vis["tipo"] == "produto", "valor_total"].sum()
        serv = vis.loc[vis["tipo"] == "servico", "valor_total"].sum()
        a, b, c, d = st.columns(4)
        with a:
            ui.card("NFs", len(vis))
        with b:
            ui.card("Valor total", ui.moeda(total))
        with c:
            ui.card("Produtos", ui.moeda(prod), "entram no estoque")
        with d:
            n_conf = int(vis["conferir"].sum())
            ui.card("A conferir", n_conf, "divergências da origem", "alerta" if n_conf else "")

        # ---- Gráficos --------------------------------------------------
        if not vis.empty:
            g1, g2 = st.columns(2)
            with g1:
                st.caption("Valor por unidade")
                por_un = vis.groupby("unidade", as_index=False)["valor_total"].sum() \
                            .sort_values("valor_total", ascending=False)
                st.bar_chart(por_un, x="unidade", y="valor_total", color=ui.AZUL, horizontal=True)
            with g2:
                st.caption("Valor por fornecedor")
                por_f = vis.groupby("fornecedor", as_index=False)["valor_total"].sum() \
                           .sort_values("valor_total", ascending=False)
                st.bar_chart(por_f, x="fornecedor", y="valor_total", color=ui.AMARELO, horizontal=True)

            if len(set(vis["mes"])) > 1:
                st.caption("Evolução mensal por unidade")
                piv = vis.pivot_table(index="mes", columns="unidade", values="valor_total",
                                      aggfunc="sum", fill_value=0)
                piv.index = [_rotulo_mes(m) for m in piv.index]
                st.dataframe(piv.map(ui.moeda), width="stretch")

        # ---- Tabela ----------------------------------------------------
        st.dataframe(
            vis[["data_emissao", "unidade", "fornecedor", "numero", "tipo", "valor_total",
                 "conferir", "observacao", "arquivo_url"]],
            hide_index=True, width="stretch",
            column_config={
                "data_emissao": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                "unidade": "Unidade", "fornecedor": "Fornecedor", "numero": "NF",
                "tipo": "Tipo",
                "valor_total": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                "conferir": st.column_config.CheckboxColumn("Conferir"),
                "observacao": "Observação",
                "arquivo_url": st.column_config.LinkColumn("Arquivo", display_text="abrir"),
            },
        )
        if not vis.empty:
            with st.expander("Ver os itens de uma NF"):
                rot = (vis["fornecedor"] + " · NF " + vis["numero"] + " · " + vis["unidade"]).tolist()
                esc = st.selectbox("NF", rot, key="nf_itens_sel")
                nf_id = int(vis.iloc[rot.index(esc)]["id"])
                it = db.query("""select descricao, unidade_nf, quantidade::float as quantidade,
                                        valor_unitario::float as valor_unitario, valor_total::float as valor_total
                                 from nfe_itens where nfe_id = :id order by id""", {"id": nf_id})
                if it.empty:
                    st.info("Esta NF não tem itens carregados (NF de serviço ou ainda não lançados).")
                else:
                    st.dataframe(it, hide_index=True, width="stretch", column_config={
                        "descricao": "Item", "unidade_nf": "Un.", "quantidade": "Qtd",
                        "valor_unitario": st.column_config.NumberColumn("Unit.", format="R$ %.2f"),
                        "valor_total": st.column_config.NumberColumn("Total", format="R$ %.2f")})
                    st.caption(f"Soma dos itens: {ui.moeda(it['valor_total'].sum())}. A diferença para o "
                               "total da NF, quando existe, é imposto de substituição (ICMS-ST).")
        st.download_button("Exportar para Excel", _excel(vis),
                           file_name=f"nfs_{date.today():%Y-%m-%d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    if not pode_editar:
        return

    st.divider()
    aba_nova, aba_editar = st.tabs(["Lançar NF", "Conferir / corrigir NF"])

    with aba_nova:
        forns = db.fornecedores_lista()
        unidades = db.locais(incluir_central=False)
        if forns.empty:
            st.warning("Cadastre o fornecedor antes de lançar a NF.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                forn = st.selectbox("Fornecedor *", forns["nome"].tolist(), key="nfn_forn")
                numero = st.text_input("Número da NF *", key="nfn_num")
            with c2:
                un = st.selectbox("Unidade (dona da NF) *", unidades["nome"].tolist(), key="nfn_un")
                data_em = st.date_input("Data de emissão *", format="DD/MM/YYYY", key="nfn_data")
            with c3:
                tipo_n = st.selectbox("Tipo *", ["produto", "servico"],
                                      format_func={"produto": "Produto (entra no estoque)",
                                                   "servico": "Serviço / locação"}.get, key="nfn_tipo")
                valor = st.number_input("Valor total (R$) *", min_value=0.0, step=10.0,
                                        format="%.2f", key="nfn_valor")
            forma = st.selectbox("Forma de pagamento",
                                 ["", "Boleto", "PIX", "Cartão Flash", "Cartão de crédito",
                                  "Transferência", "Dinheiro"], key="nfn_forma")
            link = st.text_input("Link do arquivo (Drive)", key="nfn_link")
            obs = st.text_area("Observação", key="nfn_obs")
            if st.button("Lançar NF", type="primary", key="nfn_salvar"):
                num = ui.somente_numeros(numero)
                if not num or valor <= 0:
                    st.error("Informe o número da NF e um valor maior que zero.")
                else:
                    try:
                        r = db.execute(
                            """insert into nfe (fornecedor_id, numero, tipo, data_emissao, unidade_id,
                                   valor_total, forma_pagamento, arquivo_url, observacao, criado_por)
                               values (:f, :n, :t, :d, :u, :v, :fp, :a, :o, :c) returning id""",
                            {"f": int(forns.loc[forns["nome"] == forn, "id"].iloc[0]), "n": num,
                             "t": tipo_n, "d": data_em,
                             "u": int(unidades.loc[unidades["nome"] == un, "id"].iloc[0]),
                             "v": valor, "fp": ui.vazio_para_none(forma),
                             "a": ui.vazio_para_none(link), "o": ui.vazio_para_none(obs),
                             "c": auth.usuario_atual()["id"]})
                        db.registrar("lançamento de NF", "nfe", r["id"], f"{forn} {num}")
                        for k in [k for k in st.session_state if k.startswith("nfn_")]:
                            del st.session_state[k]
                        st.success("NF lançada.")
                        st.rerun()
                    except IntegrityError:
                        st.error(f"A NF {num} de {forn} já está lançada no sistema.")

    with aba_editar:
        if df.empty:
            st.info("Nenhuma NF para conferir.")
            return
        so_pend = st.checkbox("Mostrar só as marcadas para conferir", value=True, key="nfe_pend")
        base = df[df["conferir"]] if so_pend else df
        if base.empty:
            st.success("Nenhuma NF pendente de conferência.")
            return
        rot = (base["fornecedor"] + " · NF " + base["numero"] + " · " + base["unidade"]
               + " · " + base["valor_total"].map(ui.moeda)).tolist()
        escolha = st.selectbox("NF", rot, key="nfe_sel")
        atual = base.iloc[rot.index(escolha)]
        if ui.valor(atual, "observacao"):
            st.warning(atual["observacao"])
        k = f"nfe_{int(atual['id'])}"
        unidades = db.locais(incluir_central=False)
        nomes = unidades["nome"].tolist()
        c1, c2, c3 = st.columns(3)
        with c1:
            un = st.selectbox("Unidade", nomes, index=nomes.index(atual["unidade"]), key=f"{k}_un")
        with c2:
            valor = st.number_input("Valor (R$)", min_value=0.0, value=float(atual["valor_total"]),
                                    format="%.2f", key=f"{k}_v")
        with c3:
            data_em = st.date_input("Data de emissão", value=atual["data_emissao"].date(),
                                    format="DD/MM/YYYY", key=f"{k}_d")
        link = st.text_input("Link do arquivo (Drive)", value=ui.valor(atual, "arquivo_url", ""),
                             key=f"{k}_a")
        obs = st.text_area("Observação", value=ui.valor(atual, "observacao", ""), key=f"{k}_o")
        conferida = st.checkbox("Conferida (tirar da lista de pendências)",
                                value=not bool(atual["conferir"]), key=f"{k}_c")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Salvar", type="primary", key=f"{k}_s"):
                db.execute(
                    """update nfe set unidade_id = :u, valor_total = :v, data_emissao = :d,
                           arquivo_url = :a, observacao = :o, conferir = :c where id = :id""",
                    {"u": int(unidades.loc[unidades["nome"] == un, "id"].iloc[0]), "v": valor,
                     "d": data_em, "a": ui.vazio_para_none(link), "o": ui.vazio_para_none(obs),
                     "c": not conferida, "id": int(atual["id"])})
                db.registrar("edição de NF", "nfe", int(atual["id"]),
                             f"{atual['fornecedor']} {atual['numero']}")
                st.success("NF atualizada.")
                st.rerun()
        with b2:
            if auth.tem_perfil("gestor"):
                confirma = st.checkbox("Confirmo excluir esta NF", key=f"{k}_conf_ex")
                if st.button("Excluir NF", key=f"{k}_ex", disabled=not confirma):
                    db.execute("delete from nfe where id = :id", {"id": int(atual["id"])})
                    db.registrar("exclusão de NF", "nfe", int(atual["id"]),
                                 f"{atual['fornecedor']} {atual['numero']} {atual['valor_total']}")
                    st.success("NF excluída.")
                    st.rerun()
