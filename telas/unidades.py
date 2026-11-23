"""Cadastro de unidades e da Central."""
import streamlit as st

import auth
import db
import ui


def render():
    st.title("Unidades")
    pode_editar = auth.tem_perfil("gestor")

    df = db.locais(somente_ativos=False)
    tabela = df.assign(
        tipo=df["tipo"].map({"unidade": "Unidade", "central": "Central (depósito)"}),
        recebe_via_central=df["recebe_via_central"].map({True: "Sim", False: "Não"}),
        ativo=df["ativo"].map({True: "Ativa", False: "Inativa"}),
    ).rename(columns={"nome": "Nome", "tipo": "Tipo",
                      "recebe_via_central": "Retira material da Central", "ativo": "Situação"})
    st.dataframe(tabela.drop(columns=["id"]), hide_index=True, width="stretch")
    st.caption("A Central só guarda mercadoria: o gasto de cada NFe é sempre da unidade dona da nota.")

    if not pode_editar:
        return

    aba_nova, aba_editar = st.tabs(["Nova unidade", "Editar unidade"])

    with aba_nova:
        with st.form("nova_unidade", clear_on_submit=True):
            nome = st.text_input("Nome da unidade (ex.: Manta Águas Claras)")
            via_central = st.checkbox("Retira material da Central")
            ok = st.form_submit_button("Cadastrar", type="primary")
        if ok:
            if not nome.strip():
                st.error("Informe o nome.")
            elif nome.strip().lower() in df["nome"].str.lower().tolist():
                st.error("Já existe uma unidade com esse nome.")
            else:
                r = db.execute(
                    """insert into locais (nome, tipo, recebe_via_central)
                       values (:n, 'unidade', :v) returning id""",
                    {"n": nome.strip(), "v": via_central},
                )
                db.registrar("cadastro de unidade", "locais", r["id"], nome.strip())
                st.success("Unidade cadastrada.")
                st.rerun()

    with aba_editar:
        escolha = st.selectbox("Unidade", df["nome"].tolist(), key="edit_unidade")
        linha = df[df["nome"] == escolha].iloc[0]
        k = f"un_{int(linha['id'])}"  # chave por registro: troca de seleção recarrega os valores
        nome = st.text_input("Nome", value=linha["nome"], key=f"{k}_nome")
        via_central = st.checkbox("Retira material da Central",
                                  value=bool(linha["recebe_via_central"]),
                                  disabled=linha["tipo"] == "central", key=f"{k}_vc")
        ativo = st.checkbox("Ativa", value=bool(linha["ativo"]), key=f"{k}_ativo")
        confirma = True
        if linha["ativo"] and not ativo:
            confirma = st.checkbox("Confirmo que quero DESATIVAR esta unidade "
                                   "(os dados históricos são mantidos).", key=f"{k}_conf")
        if st.button("Salvar alterações", type="primary", key=f"{k}_salvar"):
            if not nome.strip():
                st.error("Informe o nome.")
            elif not confirma:
                st.error("Marque a confirmação para desativar.")
            else:
                try:
                    db.execute(
                        """update locais set nome = :n, recebe_via_central = :v, ativo = :a
                           where id = :id""",
                        {"n": nome.strip(),
                         "v": bool(via_central) and linha["tipo"] != "central",
                         "a": ativo, "id": int(linha["id"])},
                    )
                    db.registrar("edição de unidade", "locais", int(linha["id"]), nome.strip())
                    st.success("Alterações salvas.")
                    st.rerun()
                except Exception:
                    st.error("Não foi possível salvar. Verifique se o nome já existe.")
