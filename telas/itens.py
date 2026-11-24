"""Itens comprados (das NFs): quanto cada unidade comprou de cada produto e histórico de preços."""
import pandas as pd
import streamlit as st

import db
import ui

MESES = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _rot(m: str) -> str:
    return f"{MESES[int(m[5:])]}/{m[:4]}"


def render():
    st.title("Itens comprados")
    st.caption("Itens lidos das NFs de produto. Mostra o que cada unidade comprou, "
               "em que quantidade e a que preço.")
    c1, _ = st.columns([2, 3])
    with c1:
        unidade_id, _nome = ui.filtro_unidade("it_unidade")
    filtro = "" if unidade_id is None else "and n.unidade_id = :u"
    df = db.query(
        f"""select n.data_emissao, to_char(n.data_emissao, 'YYYY-MM') as mes, l.nome as unidade,
                   coalesce(nullif(f.nome_fantasia, ''), f.razao_social) as fornecedor, n.numero as nf,
                   coalesce(p.nome, i.descricao) as produto, p.codigo, c.nome as categoria,
                   i.unidade_nf, i.quantidade::float as quantidade,
                   i.valor_total::float as valor, (i.valor_total / i.quantidade)::float as preco_unit
            from nfe_itens i
            join nfe n on n.id = i.nfe_id
            join locais l on l.id = n.unidade_id
            join fornecedores f on f.id = n.fornecedor_id
            left join produtos p on p.id = i.produto_id
            left join categorias c on c.id = p.categoria_id
            where 1=1 {filtro}""",
        {"u": unidade_id},
    )
    if df.empty:
        st.info("Nenhum item de NF carregado ainda.")
        return

    meses = sorted(df["mes"].unique(), reverse=True)
    f1, f2, f3 = st.columns([3, 2, 3])
    with f1:
        sel_m = st.multiselect("Mês", meses, format_func=_rot, key="it_meses", placeholder="Todos")
    with f2:
        cat = st.selectbox("Categoria", ["Todas"] + sorted(df["categoria"].dropna().unique()),
                           key="it_cat")
    with f3:
        busca = st.text_input("Buscar produto (ex.: papel, cloro, saco)", key="it_busca")
    vis = df.copy()
    if sel_m:
        vis = vis[vis["mes"].isin(sel_m)]
    if cat != "Todas":
        vis = vis[vis["categoria"] == cat]
    if busca.strip():
        vis = vis[vis["produto"].str.contains(busca.strip(), case=False, regex=False)]

    a, b, c = st.columns(3)
    with a:
        ui.card("Itens comprados", len(vis))
    with b:
        ui.card("Produtos diferentes", vis["produto"].nunique())
    with c:
        ui.card("Valor dos itens", ui.moeda(vis["valor"].sum()), "sem impostos de substituição")

    aba1, aba2, aba3 = st.tabs(["Por produto", "Comparar unidades", "Histórico de preço"])

    with aba1:
        res = (vis.groupby(["produto", "categoria", "unidade_nf"], dropna=False, as_index=False)
                  .agg(quantidade=("quantidade", "sum"), valor=("valor", "sum"),
                       compras=("nf", "nunique"), menor=("preco_unit", "min"),
                       maior=("preco_unit", "max"))
                  .sort_values("valor", ascending=False))
        st.dataframe(res, hide_index=True, width="stretch", column_config={
            "produto": "Produto", "categoria": "Categoria", "unidade_nf": "Un.",
            "quantidade": st.column_config.NumberColumn("Qtd comprada", format="%.2f"),
            "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
            "compras": "Nº de NFs",
            "menor": st.column_config.NumberColumn("Menor preço", format="R$ %.2f"),
            "maior": st.column_config.NumberColumn("Maior preço", format="R$ %.2f")})

    with aba2:
        st.caption("Quantidade comprada de cada produto por unidade no período filtrado.")
        piv = vis.pivot_table(index="produto", columns="unidade", values="quantidade",
                              aggfunc="sum", fill_value=0)
        piv["Total"] = piv.sum(axis=1)
        st.dataframe(piv.sort_values("Total", ascending=False), width="stretch")

    with aba3:
        prods = vis.groupby("produto")["valor"].sum().sort_values(ascending=False).index.tolist()
        prod = st.selectbox("Produto", prods, key="it_prod")
        h = df[df["produto"] == prod].sort_values("data_emissao")
        if len(h) > 1:
            st.line_chart(h, x="data_emissao", y="preco_unit", color=ui.AZUL)
        st.dataframe(h[["data_emissao", "unidade", "fornecedor", "nf", "quantidade", "preco_unit", "valor"]],
                     hide_index=True, width="stretch", column_config={
                         "data_emissao": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                         "unidade": "Unidade", "fornecedor": "Fornecedor", "nf": "NF",
                         "quantidade": "Qtd",
                         "preco_unit": st.column_config.NumberColumn("Preço unit.", format="R$ %.2f"),
                         "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f")})
        if len(h) > 1:
            var = h["preco_unit"].iloc[-1] / h["preco_unit"].iloc[0] - 1
            st.caption(f"Variação do primeiro para o último preço: {var * 100:+.1f}%")
