# Gestão Financeira

Aplicação simples de gestão financeira com Python, Streamlit e Cloud Firestore.

## Funcionalidades

- Cadastro e login por nome de usuário e senha.
- Cadastro de receitas e despesas com data, categoria e observações.
- Visualização de receitas, despesas, saldo e histórico.
- Edição e exclusão de lançamentos.

As contas ficam na coleção `users`; cada usuário possui uma subcoleção
`transactions` para seus lançamentos. As senhas não são armazenadas em texto
simples: o app salva um hash PBKDF2-SHA256 com salt individual.

## Executar

1. Instale o Python 3.10 ou superior.
2. Instale as dependências:

   ```powershell
   pip install -r requirements.txt
   ```

3. Para rodar localmente, coloque o JSON de credenciais na pasta do app com o
   nome `app-financas-826a7-firebase-adminsdk-fbsvc-1e0bc88712.json`. Também é
   possível copiar `.streamlit/secrets.toml.example` para
   `.streamlit/secrets.toml` e preencher `[firebase]` com os valores do JSON.
4. Inicie a aplicação:

   ```powershell
   streamlit run app.py
   ```

O app usa o banco Firestore `(default)`. Nunca publique o JSON da conta de
serviço nem `.streamlit/secrets.toml`; ambos são excluídos pelo `.gitignore`.

## Deploy no Streamlit Community Cloud

1. **Prepare o repositório GitHub.** Envie `app.py`, `requirements.txt`,
   `README.md` e `.gitignore`. Não envie o JSON de credenciais, `.venv`,
   `.streamlit/secrets.toml` ou outros arquivos secretos. Confirme no GitHub que
   o JSON não aparece entre os arquivos do repositório. Se a chave já foi
   enviada alguma vez, revogue-a no Google Cloud IAM e gere outra; apagar o
   arquivo em um commit posterior não remove a chave do histórico.
2. **Crie o app.** Entre em [share.streamlit.io](https://share.streamlit.io/),
   conecte sua conta GitHub e escolha **Create app**. Selecione o repositório,
   branch e `app.py` como caminho principal.
3. **Configure o secret.** Abra `.streamlit/secrets.toml.example`, substitua os
   valores de exemplo pelos valores correspondentes do JSON da conta de serviço.
   No Streamlit Cloud, abra **App settings > Secrets** e cole o conteúdo TOML
   preenchido. Não cole o JSON bruto: use o formato `[firebase]` do arquivo de
   exemplo. Salve para reiniciar o app. Para desenvolvimento local, salve esses
   mesmos valores em `.streamlit/secrets.toml`, que não deve ser enviado ao Git.
4. **Implante e teste.** Clique em **Deploy**. Nos logs, confirme que a
   instalação das dependências terminou sem erro. Abra o app, crie uma conta
   de teste e valide login, inclusão, edição e exclusão de lançamentos.
5. **Proteja o Firebase.** Confirme que o `project_id` da credencial é o
   projeto correto e que o Cloud Firestore `(default)` está ativo. Use uma
   conta de serviço dedicada, com apenas as permissões de dados do Firestore
   necessárias (por exemplo, `roles/datastore.user`), nunca Owner/Editor.
   Restrinja o acesso ao app no Streamlit Cloud quando possível, monitore
   acessos e faça rotação imediata da chave se houver suspeita de exposição.

**Importante:** o Firebase Admin SDK utilizado pelo servidor ignora as regras
de segurança do Firestore; as permissões IAM da conta de serviço e as
verificações feitas pelo app são a barreira de acesso. O login próprio deste
app é uma implementação simples e não inclui MFA, bloqueio por tentativas nem
proteção contra abuso. Para dados financeiros reais ou uso público, prefira
Firebase Authentication, limite quem pode abrir o app e faça uma revisão de
segurança antes de disponibilizar dados sensíveis.
