import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import date, datetime, time
from pathlib import Path

import firebase_admin
import streamlit as st
from firebase_admin import credentials, firestore
from google.api_core.exceptions import AlreadyExists
from google.cloud.firestore_v1 import Client
from streamlit.errors import StreamlitSecretNotFoundError


DEFAULT_CREDENTIALS = (
    Path(__file__).resolve().parent
    / "app-financas-826a7-firebase-adminsdk-fbsvc-1e0bc88712.json"
)
PASSWORD_ITERATIONS = 600_000
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")

st.set_page_config(page_title="Gestão Financeira", page_icon="💰", layout="wide")


@st.cache_resource
def get_firestore(credentials_path: str, service_account_json: str) -> Client:
    if service_account_json:
        credential = credentials.Certificate(json.loads(service_account_json))
    else:
        credential_file = Path(credentials_path)
        if not credential_file.is_file():
            raise FileNotFoundError(
                "Credenciais Firebase não encontradas. Configure o secret "
                "FIREBASE_SERVICE_ACCOUNT no Streamlit Cloud ou FIREBASE_CREDENTIALS "
                "com o caminho do arquivo JSON."
            )
        credential = credentials.Certificate(str(credential_file))

    try:
        firebase_app = firebase_admin.get_app()
    except ValueError:
        firebase_app = firebase_admin.initialize_app(credential)
    return firestore.client(app=firebase_app)


def load_firebase_service_account() -> str:
    try:
        return json.dumps(dict(st.secrets["firebase"]))
    except (KeyError, StreamlitSecretNotFoundError):
        return ""


def password_hash(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return (
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    salt_bytes = base64.urlsafe_b64decode(salt.encode("ascii"))
    _, actual_hash = password_hash(password, salt_bytes)
    return hmac.compare_digest(actual_hash, expected_hash)


def show_authentication(db: Client) -> None:
    st.title("💰 Gestão Financeira")
    st.caption("Entre na sua conta ou cadastre um novo usuário.")

    login_tab, register_tab = st.tabs(["Entrar", "Criar conta"])
    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Usuário", max_chars=30)
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar", type="primary")

        if submitted:
            normalized_username = username.strip().lower()
            if not normalized_username or not password:
                st.error("Informe o usuário e a senha.")
            else:
                try:
                    user = db.collection("users").document(normalized_username).get()
                    user_data = user.to_dict() if user.exists else None
                    if user_data and verify_password(
                        password,
                        user_data["password_salt"],
                        user_data["password_hash"],
                    ):
                        st.session_state["user"] = {
                            "id": normalized_username,
                            "username": user_data["username"],
                        }
                        st.rerun()
                    st.error("Usuário ou senha inválidos.")
                except (KeyError, ValueError) as exc:
                    st.error(f"Não foi possível validar a conta: {exc}")
                except Exception as exc:
                    st.error(f"Falha ao acessar o Firebase: {exc}")

    with register_tab:
        with st.form("register_form"):
            username = st.text_input("Nome de usuário", max_chars=30)
            password = st.text_input("Senha (mínimo de 8 caracteres)", type="password")
            confirmation = st.text_input("Confirme a senha", type="password")
            submitted = st.form_submit_button("Cadastrar", type="primary")

        if submitted:
            username = username.strip()
            if not USERNAME_PATTERN.fullmatch(username):
                st.error(
                    "Use de 3 a 30 caracteres: letras, números, ponto, hífen ou "
                    "sublinhado."
                )
            elif len(password) < 8:
                st.error("A senha deve ter pelo menos 8 caracteres.")
            elif password != confirmation:
                st.error("As senhas não conferem.")
            else:
                salt, digest = password_hash(password)
                user_ref = db.collection("users").document(username.lower())
                try:
                    user_ref.create(
                        {
                            "username": username,
                            "password_salt": salt,
                            "password_hash": digest,
                            "created_at": firestore.SERVER_TIMESTAMP,
                        }
                    )
                    st.success("Cadastro realizado. Agora você já pode entrar.")
                except AlreadyExists:
                    st.error("Esse nome de usuário já está cadastrado.")
                except Exception as exc:
                    st.error(f"Falha ao criar a conta no Firebase: {exc}")


def load_transactions(db: Client, user_id: str) -> list[dict]:
    documents = (
        db.collection("users")
        .document(user_id)
        .collection("transactions")
        .order_by("date", direction=firestore.Query.DESCENDING)
        .stream()
    )
    result = []
    for document in documents:
        transaction = document.to_dict()
        transaction["id"] = document.id
        result.append(transaction)
    return result


def transaction_date(value: datetime | date) -> date:
    return value.date() if isinstance(value, datetime) else value


def show_transaction_form(db: Client, user_id: str) -> None:
    st.subheader("Adicionar lançamento")
    with st.form("new_transaction_form", clear_on_submit=True):
        description = st.text_input("Descrição")
        col1, col2, col3 = st.columns(3)
        with col1:
            transaction_type = st.selectbox("Tipo", ["Despesa", "Receita"])
        with col2:
            amount = st.number_input("Valor (R$)", min_value=0.01, step=0.01)
        with col3:
            transaction_day = st.date_input("Data", value=date.today())
        category = st.text_input("Categoria", placeholder="Ex.: alimentação")
        notes = st.text_input("Observações")
        submitted = st.form_submit_button("Salvar lançamento", type="primary")

    if submitted:
        if not description.strip():
            st.error("Informe uma descrição para o lançamento.")
            return
        try:
            db.collection("users").document(user_id).collection(
                "transactions"
            ).add(
                {
                    "description": description.strip(),
                    "type": transaction_type,
                    "amount": round(float(amount), 2),
                    "date": datetime.combine(transaction_day, time.min),
                    "category": category.strip() or "Sem categoria",
                    "notes": notes.strip(),
                    "created_at": firestore.SERVER_TIMESTAMP,
                }
            )
            st.success("Lançamento salvo.")
            st.rerun()
        except Exception as exc:
            st.error(f"Falha ao salvar o lançamento: {exc}")


def show_transaction_management(
    db: Client, user_id: str, transactions: list[dict]
) -> None:
    st.subheader("Editar ou excluir lançamento")
    if not transactions:
        st.info("Cadastre um lançamento para habilitar a edição.")
        return

    transactions_by_id = {item["id"]: item for item in transactions}
    selected_id = st.selectbox(
        "Selecione um lançamento",
        options=list(transactions_by_id),
        format_func=lambda item_id: (
            f"{transactions_by_id[item_id]['description']} — "
            f"{transaction_date(transactions_by_id[item_id]['date']):%d/%m/%Y} — "
            f"R$ {transactions_by_id[item_id]['amount']:.2f}"
        ),
    )
    selected = transactions_by_id[selected_id]

    with st.form("edit_transaction_form"):
        description = st.text_input("Descrição", value=selected["description"])
        col1, col2, col3 = st.columns(3)
        with col1:
            transaction_type = st.selectbox(
                "Tipo",
                ["Despesa", "Receita"],
                index=0 if selected["type"] == "Despesa" else 1,
            )
        with col2:
            amount = st.number_input(
                "Valor (R$)",
                min_value=0.01,
                value=float(selected["amount"]),
                step=0.01,
            )
        with col3:
            transaction_day = st.date_input(
                "Data", value=transaction_date(selected["date"])
            )
        category = st.text_input(
            "Categoria", value=selected.get("category", "Sem categoria")
        )
        notes = st.text_input("Observações", value=selected.get("notes", ""))
        save_changes = st.form_submit_button("Salvar alterações")

    if save_changes:
        if not description.strip():
            st.error("A descrição não pode ficar vazia.")
        else:
            try:
                (
                    db.collection("users")
                    .document(user_id)
                    .collection("transactions")
                    .document(selected_id)
                    .update(
                        {
                            "description": description.strip(),
                            "type": transaction_type,
                            "amount": round(float(amount), 2),
                            "date": datetime.combine(transaction_day, time.min),
                            "category": category.strip() or "Sem categoria",
                            "notes": notes.strip(),
                        }
                    )
                )
                st.success("Lançamento atualizado.")
                st.rerun()
            except Exception as exc:
                st.error(f"Falha ao atualizar o lançamento: {exc}")

    if st.button("Excluir lançamento", type="secondary"):
        try:
            (
                db.collection("users")
                .document(user_id)
                .collection("transactions")
                .document(selected_id)
                .delete()
            )
            st.success("Lançamento excluído.")
            st.rerun()
        except Exception as exc:
            st.error(f"Falha ao excluir o lançamento: {exc}")


def show_dashboard(db: Client, user: dict) -> None:
    st.title("Gestão Financeira")
    st.write(f"Olá, **{user['username']}**!")
    if st.button("Sair"):
        del st.session_state["user"]
        st.rerun()

    try:
        transactions = load_transactions(db, user["id"])
    except Exception as exc:
        st.error(f"Falha ao carregar os lançamentos: {exc}")
        return

    income = sum(
        item["amount"] for item in transactions if item["type"] == "Receita"
    )
    expenses = sum(
        item["amount"] for item in transactions if item["type"] == "Despesa"
    )
    summary = st.columns(3)
    summary[0].metric("Receitas", f"R$ {income:.2f}")
    summary[1].metric("Despesas", f"R$ {expenses:.2f}")
    summary[2].metric("Saldo", f"R$ {income - expenses:.2f}")

    st.subheader("Lançamentos")
    if transactions:
        st.dataframe(
            [
                {
                    "Data": transaction_date(item["date"]).strftime("%d/%m/%Y"),
                    "Descrição": item["description"],
                    "Tipo": item["type"],
                    "Categoria": item.get("category", "Sem categoria"),
                    "Valor (R$)": f"{item['amount']:.2f}",
                    "Observações": item.get("notes", ""),
                }
                for item in transactions
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("Ainda não há lançamentos financeiros.")

    with st.expander("Adicionar lançamento", expanded=not transactions):
        show_transaction_form(db, user["id"])
    with st.expander("Editar ou excluir"):
        show_transaction_management(db, user["id"], transactions)


credentials_path = os.environ.get(
    "FIREBASE_CREDENTIALS", str(DEFAULT_CREDENTIALS)
)
try:
    firestore_db = get_firestore(
        credentials_path, load_firebase_service_account()
    )
except Exception as error:
    st.title("💰 Gestão Financeira")
    st.error(f"Não foi possível conectar ao Firebase: {error}")
    st.stop()

current_user = st.session_state.get("user")
if current_user:
    show_dashboard(firestore_db, current_user)
else:
    show_authentication(firestore_db)
