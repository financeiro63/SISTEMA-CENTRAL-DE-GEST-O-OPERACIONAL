"""Dashboard principal: compras do mês com detalhamento por unidade, fornecedor e item."""
import pandas as pd
import streamlit as st

import db
import ui

MESES = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _rot(m: str) -> str:
    return f"{MESES[int(m[5:])]}/{m[:4]}"


def _mes_anterior(m: str) -> str:
    ano, mes = int(m[:4]), int(m[5:])
    return f"{ano - 1}-12" if mes == 1 else f"{ano}-{mes - 1:02d}"


def _itens_mes(mes: str, filtro_nf: str, params: dict) -> pd.DataFrame:
    return db.query(
        f"""select n.id as nf_id, n.numero as nf, n.data_emissao, l.nome as unidade,
                   coalesce(nullif(f.nome_fantasia, ''), f.razao_social) as fornecedor,
                   coalesce(p.nome, i.descricao) as produto, i.produto_id, i.unidade_nf,
                   i.quantidade::float as quantidade, i.valor_total::float as valor
            from nfe_itens i
            join nfe n on n.id = i.nfe_id
            join locais l on l.id = n.unidade_id
            join fornecedores f on f.id = n.fornecedor_id
            left join produtos p on p.id = i.produto_id
            where to_char(n.data_emissao, 'YYYY-MM') = :m {filtro_nf}""",
        {**params, "m": mes})


def _resumo_itens(it: pd.DataFrame) -> pd.DataFrame:
    """Agrupa itens por produto: quantidade, valor, preço médio e nº de NFs."""
    r = (it.groupby(["produto", "unidade_nf"], as_index=False)
           .agg(quantidade=("quantidade", "sum"), valor=("valor", "sum"), nfs=("nf_id", "nunique")))
    r["preco_medio"] = r["valor"] / r["quantidade"]
    return r.sort_values("valor", ascending=False)


CFG_ITENS = {
    "produto": "Produto", "unidade_nf": "Un.",
    "quantidade": st.column_config.NumberColumn("Qtd", format="%.2f"),
    "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
    "nfs": "NFs",
    "preco_medio": st.column_config.NumberColumn("Preço médio", format="R$ %.2f"),
}


def _tabela_clicavel(df: pd.DataFrame, coluna: str, titulo: str, key: str):
    """Tabela de gasto com barra; devolve o valor da linha clicada (ou None)."""
    st.caption(titulo + " — clique numa linha para ver os itens")
    if df.empty:
        st.info("Sem dados.")
        return None
    maximo = float(df["valor"].max()) or 1.0
    ev = st.dataframe(
        df, hide_index=True, width="stretch", key=key,
        on_select="rerun", selection_mode="single-row",
        column_config={
            coluna: coluna.capitalize(),
            "nfs": "NFs",
            "valor": st.column_config.ProgressColumn("Valor", format="R$ %.2f",
                                                     min_value=0, max_value=maximo),
        },
    )
    linhas = ev.selection.rows if ev and ev.selection else []
    return df.iloc[linhas[0]][coluna] if linhas else None


def _mostrar_itens(it: pd.DataFrame, nfs_mes: pd.DataFrame, rotulo: str):
    st.markdown(f"#### Itens comprados — {rotulo}")
    if it.empty:
        st.info("Nenhum item de produto neste filtro. As NFs de serviço (locação, manutenção) "
                "não têm itens de estoque.")
    else:
        st.dataframe(_resumo_itens(it), hide_index=True, width="stretch", column_config=CFG_ITENS)
    # NFs do filtro, com os itens de cada uma
    with st.expander(f"Ver NF por NF ({len(nfs_mes)} NFs)"):
        for _, nf in nfs_mes.sort_values("data_emissao").iterrows():
            st.markdown(f"**NF {nf['numero']}** · {nf['fornecedor']} · {nf['unidade']} · "
                        f"{pd.to_datetime(nf['data_emissao']):%d/%m/%Y} · {ui.moeda(nf['valor'])}"
                        + (" · *serviço*" if nf["tipo"] == "servico" else ""))
            itn = it[it["nf_id"] == nf["id"]]
            if not itn.empty:
                st.dataframe(itn[["produto", "unidade_nf", "quantidade", "valor"]], hide_index=True,
                             width="stretch", column_config=CFG_ITENS)


def render():
    st.title("Dashboard")
    c1, c2 = st.columns([2, 2])
    with c1:
        unidade_id, unidade_nome = ui.filtro_unidade("dash_unidade")
    params = {"u": unidade_id}
    filtro_nf = "" if unidade_id is None else "and n.unidade_id = :u"

    meses = db.query(f"""select distinct to_char(data_emissao, 'YYYY-MM') as mes
                         from nfe n where 1=1 {filtro_nf} order by 1 desc""", params)["mes"].tolist()
    if not meses:
        st.info("Nenhuma NF lançada ainda.")
        return
    with c2:
        mes = st.selectbox("Mês de emissão", meses, format_func=_rot, key="dash_mes")
    ant = _mes_anterior(mes)

    nfs = db.query(
        f"""select n.id, n.numero, n.data_emissao, n.tipo, n.valor_total::float as valor, n.conferir,
                   l.nome as unidade, coalesce(nullif(f.nome_fantasia, ''), f.razao_social) as fornecedor
            from nfe n join locais l on l.id = n.unidade_id
            join fornecedores f on f.id = n.fornecedor_id
            where to_char(n.data_emissao, 'YYYY-MM') = :m {filtro_nf}""",
        {**params, "m": mes})
    total_ant = db.query_one(
        f"""select coalesce(sum(valor_total), 0)::float as v from nfe n
            where to_char(data_emissao, 'YYYY-MM') = :m {filtro_nf}""", {**params, "m": ant})["v"]
    itens = _itens_mes(mes, filtro_nf, params)
    itens_ant = _itens_mes(ant, filtro_nf, params)

    # ---- Indicadores do mês --------------------------------------------
    total = nfs["valor"].sum()
    var = f"{(total / total_ant - 1) * 100:+.0f}% vs {_rot(ant)}" if total_ant else "sem mês anterior"
    st.subheader(f"Compras — {_rot(mes)} · {unidade_nome}")
    a, b, c, d = st.columns(4)
    with a:
        ui.card("Valor comprado", ui.moeda(total), var)
    with b:
        ui.card("NFs no mês", len(nfs), f"{int((nfs['tipo'] == 'produto').sum())} de produto")
    with c:
        ui.card("Serviços / locação", ui.moeda(nfs.loc[nfs["tipo"] == "servico", "valor"].sum()),
                "não geram estoque")
    with d:
        n_c = int(nfs["conferir"].sum())
        ui.card("NFs a conferir", n_c, "divergências", "alerta" if n_c else "")

    # ---- Gasto por unidade e por fornecedor (clicáveis) -------------------
    g1, g2 = st.columns(2)
    por_un = (nfs.groupby("unidade", as_index=False)
                 .agg(valor=("valor", "sum"), nfs=("id", "count"))
                 .sort_values("valor", ascending=False))
    por_f = (nfs.groupby("fornecedor", as_index=False)
                .agg(valor=("valor", "sum"), nfs=("id", "count"))
                .sort_values("valor", ascending=False))
    with g1:
        un_sel = _tabela_clicavel(por_un, "unidade", "Gasto por unidade", f"tb_un_{mes}_{unidade_id}")
    with g2:
        f_sel = _tabela_clicavel(por_f, "fornecedor", "Gasto por fornecedor", f"tb_f_{mes}_{unidade_id}")

    if un_sel or f_sel:
        it_f, nf_f, partes = itens, nfs, []
        if un_sel:
            it_f, nf_f = it_f[it_f["unidade"] == un_sel], nf_f[nf_f["unidade"] == un_sel]
            partes.append(un_sel)
        if f_sel:
            it_f, nf_f = it_f[it_f["fornecedor"] == f_sel], nf_f[nf_f["fornecedor"] == f_sel]
            partes.append(f_sel)
        _mostrar_itens(it_f, nf_f, " · ".join(partes) + f" · {_rot(mes)}")
        st.caption("Dica: clique de novo na linha marcada para desmarcar.")

    st.divider()

    # ---- Itens mais comprados ----------------------------------------------
    st.subheader("Itens mais comprados no mês")
    if itens.empty:
        st.info("Sem itens de produto neste mês.")
    else:
        res = _resumo_itens(itens)
        t1, t2 = st.tabs(["Por valor", "Por frequência (nº de NFs)"])
        with t1:
            st.dataframe(res.head(15), hide_index=True, width="stretch", column_config=CFG_ITENS)
        with t2:
            st.dataframe(res.sort_values(["nfs", "valor"], ascending=False).head(15),
                         hide_index=True, width="stretch", column_config=CFG_ITENS)

    # ---- Variação de preço vs mês anterior ----------------------------------
    st.subheader(f"Variação de preço — {_rot(mes)} vs {_rot(ant)}")
    st.caption("Preço médio pago por unidade de medida (valor ÷ quantidade), mesmo produto e "
               "mesma embalagem. Só aparecem produtos comprados nos dois meses.")
    if itens.empty or itens_ant.empty:
        st.info("É preciso ter itens nos dois meses para comparar.")
    else:
        def preco(df):
            g = (df[df["produto_id"].notna()]
                 .groupby(["produto_id", "produto", "unidade_nf"], as_index=False)
                 .agg(valor=("valor", "sum"), quantidade=("quantidade", "sum")))
            g["preco"] = g["valor"] / g["quantidade"]
            return g[["produto_id", "produto", "unidade_nf", "preco"]]
        comp = preco(itens).merge(preco(itens_ant), on=["produto_id", "produto", "unidade_nf"],
                                  suffixes=("_atual", "_anterior"))
        comp["variacao"] = comp["preco_atual"] / comp["preco_anterior"] - 1
        comp["diferenca"] = comp["preco_atual"] - comp["preco_anterior"]
        cfg = {"produto": "Produto", "unidade_nf": "Un.",
               "preco_anterior": st.column_config.NumberColumn(_rot(ant), format="R$ %.2f"),
               "preco_atual": st.column_config.NumberColumn(_rot(mes), format="R$ %.2f"),
               "diferenca": st.column_config.NumberColumn("Diferença", format="R$ %.2f"),
               "variacao": st.column_config.NumberColumn("Variação", format="percent")}
        cols = ["produto", "unidade_nf", "preco_anterior", "preco_atual", "diferenca", "variacao"]
        subiu = comp[comp["variacao"] > 0.005].sort_values("variacao", ascending=False)
        caiu = comp[comp["variacao"] < -0.005].sort_values("variacao")
        v1, v2 = st.columns(2)
        with v1:
            st.markdown(f"**🔺 Preço subiu ({len(subiu)})**")
            st.dataframe(subiu[cols], hide_index=True, width="stretch", column_config=cfg)
        with v2:
            st.markdown(f"**🔻 Preço caiu ({len(caiu)})**")
            st.dataframe(caiu[cols], hide_index=True, width="stretch", column_config=cfg)
        iguais = len(comp) - len(subiu) - len(caiu)
        st.caption(f"{len(comp)} produtos comparados · {iguais} com preço igual.")

    st.divider()

    # ---- Cadastros ----------------------------------------------------------
    n_prod = db.query_one("select count(*) as n from produtos where ativo")["n"]
    n_forn = db.query_one("select count(*) as n from fornecedores where ativo")["n"]
    n_unid = db.query_one("select count(*) as n from locais where ativo and tipo = 'unidade'")["n"]
    a, b, c = st.columns(3)
    with a:
        ui.card("Unidades ativas", n_unid)
    with b:
        ui.card("Produtos cadastrados", n_prod)
    with c:
        ui.card("Fornecedores", n_forn)
