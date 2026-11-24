"""Dashboard principal."""
import streamlit as st

import db
import ui


def render():
    st.title("Dashboard")
    c1, _ = st.columns([2, 3])
    with c1:
        unidade_id, unidade_nome = ui.filtro_unidade("dash_unidade")

    filtro_saldo = "" if unidade_id is None else "and s.unidade_dona_id = :u"
    params = {"u": unidade_id}

    # ---- Indicadores que já funcionam na Fase 1 ---------------------
    n_prod = db.query_one("select count(*) as n from produtos where ativo")["n"]
    n_forn = db.query_one("select count(*) as n from fornecedores where ativo")["n"]
    n_unid = db.query_one("select count(*) as n from locais where ativo and tipo = 'unidade'")["n"]

    # Estoque baixo / em falta: soma o saldo da unidade (Central + unidade)
    saldos = db.query(
        f"""select p.nome as produto, l.nome as unidade,
                   sum(s.quantidade) as saldo, p.estoque_minimo as minimo, p.unidade_medida
            from estoque_saldos s
            join produtos p on p.id = s.produto_id and p.ativo
            join locais l on l.id = s.unidade_dona_id
            where p.estoque_minimo > 0 {filtro_saldo}
            group by p.nome, l.nome, p.estoque_minimo, p.unidade_medida""",
        params,
    )
    em_falta = saldos[saldos["saldo"] <= 0]
    baixo = saldos[(saldos["saldo"] > 0) & (saldos["saldo"] <= saldos["minimo"])]

    st.subheader(f"Visão geral — {unidade_nome}")
    a, b, c, d, e = st.columns(5)
    with a:
        ui.card("Unidades ativas", n_unid)
    with b:
        ui.card("Produtos cadastrados", n_prod)
    with c:
        ui.card("Fornecedores", n_forn)
    with d:
        ui.card("Estoque baixo", len(baixo), "no mínimo ou abaixo", "alerta" if len(baixo) else "")
    with e:
        ui.card("Produtos em falta", len(em_falta), "saldo zerado", "alerta" if len(em_falta) else "")

    # ---- Compras do mês (NFs) -----------------------------------------
    filtro_nf = "" if unidade_id is None else "and n.unidade_id = :u"
    meses = db.query(f"""select distinct to_char(data_emissao, 'YYYY-MM') as mes
                         from nfe n where 1=1 {filtro_nf} order by 1 desc""", params)["mes"].tolist()
    st.subheader("Compras (NFs lançadas)")
    if not meses:
        st.info("Nenhuma NF lançada ainda.")
    else:
        rot = {m: f"{['','Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'][int(m[5:])]}/{m[:4]}"
               for m in meses}
        mes = st.selectbox("Mês de emissão", meses, format_func=rot.get, key="dash_mes")
        nf = db.query(
            f"""select l.nome as unidade, coalesce(nullif(f.nome_fantasia, ''), f.razao_social) as fornecedor,
                       n.tipo, n.valor_total::float as valor, n.conferir
                from nfe n join locais l on l.id = n.unidade_id
                join fornecedores f on f.id = n.fornecedor_id
                where to_char(n.data_emissao, 'YYYY-MM') = :m {filtro_nf}""",
            {**params, "m": mes})
        idx = meses.index(mes)
        anterior = None
        if idx + 1 < len(meses):
            anterior = db.query_one(
                f"""select coalesce(sum(valor_total), 0)::float as v from nfe n
                    where to_char(data_emissao, 'YYYY-MM') = :m {filtro_nf}""",
                {**params, "m": meses[idx + 1]})["v"]
        total = nf["valor"].sum()
        var = ""
        if anterior:
            var = f"{(total / anterior - 1) * 100:+.0f}% vs {rot[meses[idx + 1]]}"
        a, b, c, d = st.columns(4)
        with a:
            ui.card("Compras no mês", len(nf), "NFs lançadas")
        with b:
            ui.card("Valor total comprado", ui.moeda(total), var)
        with c:
            ui.card("Produtos / Serviços",
                    f"{ui.moeda(nf.loc[nf['tipo'] == 'produto', 'valor'].sum())}",
                    f"serviços: {ui.moeda(nf.loc[nf['tipo'] == 'servico', 'valor'].sum())}")
        with d:
            n_c = int(nf["conferir"].sum())
            ui.card("NFs a conferir", n_c, "divergências", "alerta" if n_c else "")
        g1, g2 = st.columns(2)
        with g1:
            st.caption("Gastos por unidade")
            st.bar_chart(nf.groupby("unidade", as_index=False)["valor"].sum()
                           .sort_values("valor", ascending=False),
                         x="unidade", y="valor", color=ui.AZUL, horizontal=True)
        with g2:
            st.caption("Gastos por fornecedor")
            st.bar_chart(nf.groupby("fornecedor", as_index=False)["valor"].sum()
                           .sort_values("valor", ascending=False),
                         x="fornecedor", y="valor", color=ui.AMARELO, horizontal=True)

    # ---- Indicadores das próximas fases (estrutura já reservada) ----
    st.subheader("Próximos módulos")
    futuros = [
        ("Solicitações pendentes", "Fase 2"), ("Solicitações em andamento", "Fase 2"),
        ("Manutenções pendentes", "Fase 3"), ("Consumo de materiais", "Fase 3"),
    ]
    cols = st.columns(4)
    for i, (rotulo, fase) in enumerate(futuros):
        with cols[i % 4]:
            ui.card(rotulo, "—", f"disponível na {fase}", "inativo")

    # ---- Listas de alerta -------------------------------------------
    if len(baixo) or len(em_falta):
        st.subheader("Itens que precisam de atenção")
        t1, t2 = st.tabs([f"Em falta ({len(em_falta)})", f"Estoque baixo ({len(baixo)})"])
        with t1:
            st.dataframe(em_falta, hide_index=True, width="stretch")
        with t2:
            st.dataframe(baixo, hide_index=True, width="stretch")

    # ---- Cadastro por categoria ---------------------------------------
    st.subheader("Cadastros por categoria")
    g1, g2 = st.columns(2)
    prod_cat = db.query(
        """select coalesce(c.nome, 'Sem categoria') as categoria, count(*) as produtos
           from produtos p left join categorias c on c.id = p.categoria_id
           where p.ativo group by 1 order by 2 desc"""
    )
    forn_cat = db.query(
        """select c.nome as categoria, count(*) as fornecedores
           from fornecedor_categorias fc
           join categorias c on c.id = fc.categoria_id
           join fornecedores f on f.id = fc.fornecedor_id and f.ativo
           group by 1 order by 2 desc"""
    )
    with g1:
        st.caption("Produtos por categoria")
        if prod_cat.empty:
            st.info("Nenhum produto cadastrado ainda.")
        else:
            st.bar_chart(prod_cat, x="categoria", y="produtos", color=ui.AZUL, horizontal=True)
    with g2:
        st.caption("Fornecedores por categoria")
        if forn_cat.empty:
            st.info("Nenhum fornecedor cadastrado ainda.")
        else:
            st.bar_chart(forn_cat, x="categoria", y="fornecedores", color=ui.AMARELO, horizontal=True)
