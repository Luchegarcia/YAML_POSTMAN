import tkinter as tk
from tkinter import (
    filedialog,
    messagebox,
    ttk
)

import yaml
import json
import re
import uuid

from pathlib import Path


# ============================================================
# FUNÇÕES DE CONVERSÃO
# ============================================================

def extrair_variaveis(texto):
    """
    Localiza variáveis no padrão:
    {{nomeVariavel}}
    """

    if texto is None:
        return set()

    return set(
        re.findall(
            r"\{\{([^{}]+)\}\}",
            str(texto)
        )
    )


def extrair_variaveis_recursivamente(objeto):
    """
    Procura {{variaveis}} recursivamente
    dentro de dict, list e strings.
    """

    variaveis = set()

    if isinstance(objeto, dict):

        for chave, valor in objeto.items():

            variaveis.update(
                extrair_variaveis(chave)
            )

            variaveis.update(
                extrair_variaveis_recursivamente(
                    valor
                )
            )

    elif isinstance(objeto, list):

        for item in objeto:

            variaveis.update(
                extrair_variaveis_recursivamente(
                    item
                )
            )

    elif isinstance(objeto, str):

        variaveis.update(
            extrair_variaveis(objeto)
        )

    return variaveis


def converter_headers(headers_yaml):
    """
    Converte headers para Postman Collection v2.1.

    Suporta:

    headers:
      Content-Type: application/json
      Authorization: Bearer ...

    Também aceita listas.
    """

    resultado = []

    if not headers_yaml:
        return resultado

    # Headers como objeto/dicionário
    if isinstance(headers_yaml, dict):

        for chave, valor in headers_yaml.items():

            resultado.append({
                "key": str(chave),
                "value": str(valor),
                "type": "text"
            })

    # Headers eventualmente já em formato de lista
    elif isinstance(headers_yaml, list):

        for header in headers_yaml:

            if isinstance(header, dict):

                chave = (
                    header.get("key")
                    or header.get("name")
                    or ""
                )

                valor = (
                    header.get("value")
                    or ""
                )

                if chave:

                    resultado.append({
                        "key": str(chave),
                        "value": str(valor),
                        "type": "text"
                    })

    return resultado


def converter_url(url):
    """
    Monta estrutura de URL do Postman.
    """

    if not url:
        return {
            "raw": ""
        }

    url = str(url).strip()

    resultado = {
        "raw": url
    }

    # --------------------------------------------------------
    # Caso:
    # {{baseUrl}}/api/cliente/v1/clientes
    # --------------------------------------------------------

    match_variavel = re.match(
        r"^(\{\{[^{}]+\}\})(.*)$",
        url
    )

    if match_variavel:

        host = match_variavel.group(1)

        restante = (
            match_variavel
            .group(2)
            .lstrip("/")
        )

        resultado["host"] = [
            host
        ]

        if restante:

            caminho_sem_query = restante.split("?")[0]

            resultado["path"] = [
                parte
                for parte
                in caminho_sem_query.split("/")
                if parte
            ]

        return resultado

    # --------------------------------------------------------
    # URL absoluta
    # --------------------------------------------------------

    match_absoluta = re.match(
        r"^(https?)://([^/]+)(.*)$",
        url
    )

    if match_absoluta:

        protocolo = match_absoluta.group(1)

        host = match_absoluta.group(2)

        restante = (
            match_absoluta
            .group(3)
            .lstrip("/")
        )

        resultado["protocol"] = protocolo

        resultado["host"] = host.split(".")

        if restante:

            caminho_sem_query = restante.split("?")[0]

            resultado["path"] = [
                parte
                for parte
                in caminho_sem_query.split("/")
                if parte
            ]

    return resultado


def converter_body(body_yaml):
    """
    Converte o body para formato Postman.
    """

    if not body_yaml:
        return None

    # --------------------------------------------------------
    # Formato:
    #
    # body:
    #   type: json
    #   content: |
    #       {...}
    # --------------------------------------------------------

    if isinstance(body_yaml, dict):

        conteudo = body_yaml.get("content")

        if conteudo is not None:

            linguagem = "json"

            tipo = str(
                body_yaml.get("type", "")
            ).lower()

            if tipo in (
                "text",
                "xml",
                "html"
            ):
                linguagem = tipo

            return {
                "mode": "raw",
                "raw": str(conteudo),
                "options": {
                    "raw": {
                        "language": linguagem
                    }
                }
            }

        # Caso body já seja um objeto JSON/YAML
        try:

            conteudo_json = json.dumps(
                body_yaml,
                ensure_ascii=False,
                indent=2
            )

            return {
                "mode": "raw",
                "raw": conteudo_json,
                "options": {
                    "raw": {
                        "language": "json"
                    }
                }
            }

        except Exception:
            pass

    # String direta
    elif isinstance(body_yaml, str):

        return {
            "mode": "raw",
            "raw": body_yaml,
            "options": {
                "raw": {
                    "language": "json"
                }
            }
        }

    return None


def converter_scripts(scripts_yaml):
    """
    Converte scripts do formato novo.

    beforeRequest  -> prerequest
    afterResponse  -> test
    """

    eventos = []

    if not scripts_yaml:
        return eventos

    if not isinstance(scripts_yaml, list):
        return eventos

    for script in scripts_yaml:

        if not isinstance(script, dict):
            continue

        tipo = script.get("type", "")

        codigo = script.get("code", "")

        if isinstance(codigo, list):

            linhas = [
                str(linha)
                for linha in codigo
            ]

        else:

            linhas = str(
                codigo
            ).splitlines()

        # --------------------------------------------
        # After Response => Tests
        # --------------------------------------------

        if tipo == "afterResponse":

            eventos.append({
                "listen": "test",
                "script": {
                    "type": "text/javascript",
                    "exec": linhas
                }
            })

        # --------------------------------------------
        # Before Request => Pre-request Script
        # --------------------------------------------

        elif tipo == "beforeRequest":

            eventos.append({
                "listen": "prerequest",
                "script": {
                    "type": "text/javascript",
                    "exec": linhas
                }
            })

    return eventos


def obter_nome_request(
    dados,
    caminho_arquivo
):
    """
    Tenta obter um nome amigável para a requisição.
    """

    nome = (
        dados.get("name")
        or dados.get("title")
    )

    if nome:
        return str(nome)

    nome = Path(
        caminho_arquivo
    ).stem

    # remove .request
    if nome.lower().endswith(".request"):

        nome = nome[:-8]

    return nome


def converter_request(
    dados,
    caminho_arquivo
):
    """
    Converte um YAML para um item Postman.
    """

    nome = obter_nome_request(
        dados,
        caminho_arquivo
    )

    request = {
        "method": str(
            dados.get(
                "method",
                "GET"
            )
        ).upper(),

        "header": converter_headers(
            dados.get("headers")
        ),

        "url": converter_url(
            dados.get(
                "url",
                ""
            )
        )
    }

    # Descrição

    descricao = dados.get(
        "description"
    )

    if descricao:

        request["description"] = str(
            descricao
        )

    # Body

    body = converter_body(
        dados.get("body")
    )

    if body:

        request["body"] = body

    # Scripts

    eventos = converter_scripts(
        dados.get("scripts")
    )

    item = {
        "name": nome,
        "request": request,
        "response": []
    }

    if eventos:

        item["event"] = eventos

    return item


def ler_yaml(caminho):
    """
    Lê o arquivo YAML.
    """

    with open(
        caminho,
        "r",
        encoding="utf-8"
    ) as arquivo:

        dados = yaml.safe_load(
            arquivo
        )

    if not dados:

        raise ValueError(
            "Arquivo YAML vazio."
        )

    if not isinstance(dados, dict):

        raise ValueError(
            "Estrutura YAML não reconhecida."
        )

    return dados


def criar_collection(
    nome_collection,
    itens,
    variaveis
):
    """
    Cria estrutura Postman Collection v2.1.
    """

    collection = {

        "info": {

            "_postman_id": str(
                uuid.uuid4()
            ),

            "name": nome_collection,

            "schema":
                "https://schema.getpostman.com/"
                "json/collection/v2.1.0/"
                "collection.json"
        },

        "item": itens
    }

    if variaveis:

        collection["variable"] = [

            {
                "key": variavel,
                "value": ""
            }

            for variavel
            in sorted(variaveis)
        ]

    return collection


def salvar_json(
    dados,
    destino
):

    with open(
        destino,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            dados,
            arquivo,
            ensure_ascii=False,
            indent=2
        )


def nome_arquivo_seguro(nome):
    """
    Remove caracteres problemáticos
    para nomes de arquivo.
    """

    nome = re.sub(
        r'[<>:"/\\|?*]',
        "_",
        nome
    )

    return nome.strip()


# ============================================================
# INTERFACE TKINTER
# ============================================================

class ConversorPostmanApp:

    def __init__(self, root):

        self.root = root
        self.root.iconbitmap("yaml_json_converter.ico")

        self.root.title(
            "Conversor YAML para Postman Collection JSON"
        )

        self.root.geometry(
            "850x650"
        )

        self.root.minsize(
            750,
            550
        )

        self.arquivos = []

        self.pasta_saida = tk.StringVar()

        self.tipo_conversao = tk.StringVar(
            value="collection"
        )

        self.nome_collection = tk.StringVar(
            value="Minha Collection"
        )

        self.criar_interface()

    # ========================================================
    # INTERFACE
    # ========================================================

    def criar_interface(self):

        frame_principal = ttk.Frame(
            self.root,
            padding=15
        )

        frame_principal.pack(
            fill="both",
            expand=True
        )

        # ====================================================
        # TÍTULO
        # ====================================================

        titulo = ttk.Label(
            frame_principal,
            text="Conversor YAML para JSON - Versões Antigas do Postman",
            font=(
                "Segoe UI",
                16,
                "bold"
            )
        )

        titulo.pack(
            anchor="w",
            pady=(0, 10)
        )

        descricao = ttk.Label(
            frame_principal,
            text=(
                "Selecione um ou vários arquivos YAML "
                "e converta para Postman Collection v2.1."
            )
        )

        descricao.pack(
            anchor="w",
            pady=(0, 15)
        )

        # ====================================================
        # ARQUIVOS
        # ====================================================

        frame_arquivos = ttk.LabelFrame(
            frame_principal,
            text="Arquivos YAML",
            padding=10
        )

        frame_arquivos.pack(
            fill="both",
            expand=True
        )

        frame_botoes = ttk.Frame(
            frame_arquivos
        )

        frame_botoes.pack(
            fill="x",
            pady=(0, 8)
        )

        ttk.Button(
            frame_botoes,
            text="Selecionar arquivos",
            command=self.selecionar_arquivos
        ).pack(
            side="left",
            padx=(0, 5)
        )

        ttk.Button(
            frame_botoes,
            text="Remover selecionado",
            command=self.remover_selecionados
        ).pack(
            side="left",
            padx=5
        )

        ttk.Button(
            frame_botoes,
            text="Limpar lista",
            command=self.limpar_lista
        ).pack(
            side="left",
            padx=5
        )

        # Listbox

        frame_lista = ttk.Frame(
            frame_arquivos
        )

        frame_lista.pack(
            fill="both",
            expand=True
        )

        self.lista = tk.Listbox(
            frame_lista,
            selectmode=tk.EXTENDED,
            height=9
        )

        self.lista.pack(
            side="left",
            fill="both",
            expand=True
        )

        scrollbar = ttk.Scrollbar(
            frame_lista,
            orient="vertical",
            command=self.lista.yview
        )

        scrollbar.pack(
            side="right",
            fill="y"
        )

        self.lista.configure(
            yscrollcommand=scrollbar.set
        )

        # ====================================================
        # OPÇÕES
        # ====================================================

        frame_opcoes = ttk.LabelFrame(
            frame_principal,
            text="Tipo de conversão",
            padding=10
        )

        frame_opcoes.pack(
            fill="x",
            pady=10
        )

        ttk.Radiobutton(
            frame_opcoes,
            text=(
                "Gerar uma única Collection "
                "com todas as requisições"
            ),
            variable=self.tipo_conversao,
            value="collection",
            command=self.atualizar_estado
        ).pack(
            anchor="w"
        )

        ttk.Radiobutton(
            frame_opcoes,
            text=(
                "Gerar uma Collection JSON "
                "para cada YAML"
            ),
            variable=self.tipo_conversao,
            value="individual",
            command=self.atualizar_estado
        ).pack(
            anchor="w",
            pady=(5, 0)
        )

        # ====================================================
        # NOME COLLECTION
        # ====================================================

        frame_nome = ttk.Frame(
            frame_opcoes
        )

        frame_nome.pack(
            fill="x",
            pady=(10, 0)
        )

        ttk.Label(
            frame_nome,
            text="Nome da Collection:"
        ).pack(
            side="left"
        )

        self.entry_collection = ttk.Entry(
            frame_nome,
            textvariable=self.nome_collection
        )

        self.entry_collection.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(10, 0)
        )

        # ====================================================
        # PASTA DE SAÍDA
        # ====================================================

        frame_saida = ttk.LabelFrame(
            frame_principal,
            text="Pasta de saída",
            padding=10
        )

        frame_saida.pack(
            fill="x",
            pady=(0, 10)
        )

        ttk.Entry(
            frame_saida,
            textvariable=self.pasta_saida
        ).pack(
            side="left",
            fill="x",
            expand=True
        )

        ttk.Button(
            frame_saida,
            text="Selecionar",
            command=self.selecionar_pasta_saida
        ).pack(
            side="left",
            padx=(8, 0)
        )

        # ====================================================
        # CONVERTER
        # ====================================================

        ttk.Button(
            frame_principal,
            text="CONVERTER",
            command=self.converter
        ).pack(
            fill="x",
            pady=(0, 10),
            ipady=5
        )

        # ====================================================
        # LOG
        # ====================================================

        frame_log = ttk.LabelFrame(
            frame_principal,
            text="Resultado",
            padding=8
        )

        frame_log.pack(
            fill="both",
            expand=True
        )

        self.log = tk.Text(
            frame_log,
            height=8,
            state="disabled",
            font=(
                "Consolas",
                9
            )
        )

        self.log.pack(
            fill="both",
            expand=True
        )

    # ========================================================
    # AÇÕES
    # ========================================================

    def selecionar_arquivos(self):

        arquivos = filedialog.askopenfilenames(

            title="Selecionar arquivos YAML",

            filetypes=[
                (
                    "Arquivos YAML",
                    "*.yaml *.yml"
                ),
                (
                    "Todos os arquivos",
                    "*.*"
                )
            ]
        )

        if not arquivos:
            return

        for arquivo in arquivos:

            if arquivo not in self.arquivos:

                self.arquivos.append(
                    arquivo
                )

                self.lista.insert(
                    tk.END,
                    arquivo
                )

        # Define automaticamente pasta de saída
        if (
            not self.pasta_saida.get()
            and self.arquivos
        ):

            self.pasta_saida.set(
                str(
                    Path(
                        self.arquivos[0]
                    ).parent
                )
            )

        self.escrever_log(
            f"{len(arquivos)} arquivo(s) adicionado(s)."
        )

    def remover_selecionados(self):

        selecionados = list(
            self.lista.curselection()
        )

        if not selecionados:
            return

        for indice in reversed(
            selecionados
        ):

            self.lista.delete(
                indice
            )

            del self.arquivos[
                indice
            ]

    def limpar_lista(self):

        self.arquivos.clear()

        self.lista.delete(
            0,
            tk.END
        )

        self.escrever_log(
            "Lista de arquivos limpa."
        )

    def selecionar_pasta_saida(self):

        pasta = filedialog.askdirectory(
            title="Selecionar pasta de saída"
        )

        if pasta:

            self.pasta_saida.set(
                pasta
            )

    def atualizar_estado(self):

        if (
            self.tipo_conversao.get()
            == "collection"
        ):

            self.entry_collection.configure(
                state="normal"
            )

        else:

            self.entry_collection.configure(
                state="disabled"
            )

    # ========================================================
    # LOG
    # ========================================================

    def escrever_log(
        self,
        mensagem
    ):

        self.log.configure(
            state="normal"
        )

        self.log.insert(
            tk.END,
            mensagem + "\n"
        )

        self.log.see(
            tk.END
        )

        self.log.configure(
            state="disabled"
        )

        self.root.update_idletasks()

    # ========================================================
    # CONVERSÃO
    # ========================================================

    def converter(self):

        if not self.arquivos:

            messagebox.showwarning(
                "Atenção",
                "Selecione pelo menos um arquivo YAML."
            )

            return

        pasta_saida = self.pasta_saida.get()

        if not pasta_saida:

            messagebox.showwarning(
                "Atenção",
                "Selecione a pasta de saída."
            )

            return

        pasta_saida = Path(
            pasta_saida
        )

        pasta_saida.mkdir(
            parents=True,
            exist_ok=True
        )

        self.escrever_log(
            "=" * 60
        )

        self.escrever_log(
            "Iniciando conversão..."
        )

        modo = (
            self.tipo_conversao.get()
        )

        try:

            if modo == "collection":

                self.converter_collection_unica(
                    pasta_saida
                )

            else:

                self.converter_individual(
                    pasta_saida
                )

        except Exception as erro:

            self.escrever_log(
                f"ERRO: {erro}"
            )

            messagebox.showerror(
                "Erro",
                str(erro)
            )

    # ========================================================
    # COLLECTION ÚNICA
    # ========================================================

    def converter_collection_unica(
        self,
        pasta_saida
    ):

        nome_collection = (
            self.nome_collection
            .get()
            .strip()
        )

        if not nome_collection:

            nome_collection = (
                "Postman Collection"
            )

        itens = []

        todas_variaveis = set()

        erros = []

        for caminho in self.arquivos:

            try:

                dados = ler_yaml(
                    caminho
                )

                item = converter_request(
                    dados,
                    caminho
                )

                itens.append(
                    item
                )

                variaveis = (
                    extrair_variaveis_recursivamente(
                        dados
                    )
                )

                todas_variaveis.update(
                    variaveis
                )

                self.escrever_log(
                    f"OK: {Path(caminho).name}"
                )

            except Exception as erro:

                mensagem = (
                    f"{Path(caminho).name}: {erro}"
                )

                erros.append(
                    mensagem
                )

                self.escrever_log(
                    f"ERRO: {mensagem}"
                )

        if not itens:

            raise Exception(
                "Nenhum arquivo pôde ser convertido."
            )

        collection = criar_collection(
            nome_collection,
            itens,
            todas_variaveis
        )

        nome_saida = (
            nome_arquivo_seguro(
                nome_collection
            )
            +
            ".postman_collection.json"
        )

        destino = (
            pasta_saida
            /
            nome_saida
        )

        salvar_json(
            collection,
            destino
        )

        self.escrever_log(
            ""
        )

        self.escrever_log(
            f"Collection criada: {destino}"
        )

        self.escrever_log(
            f"Requisições: {len(itens)}"
        )

        self.escrever_log(
            f"Variáveis: {len(todas_variaveis)}"
        )

        messagebox.showinfo(
            "Conversão concluída",
            (
                "Collection criada com sucesso.\n\n"
                f"Requisições: {len(itens)}\n"
                f"Arquivo:\n{destino}"
            )
        )

    # ========================================================
    # COLLECTION INDIVIDUAL
    # ========================================================

    def converter_individual(
        self,
        pasta_saida
    ):

        quantidade = 0

        erros = 0

        for caminho in self.arquivos:

            try:

                dados = ler_yaml(
                    caminho
                )

                item = converter_request(
                    dados,
                    caminho
                )

                variaveis = (
                    extrair_variaveis_recursivamente(
                        dados
                    )
                )

                nome = obter_nome_request(
                    dados,
                    caminho
                )

                collection = criar_collection(
                    nome,
                    [item],
                    variaveis
                )

                nome_saida = (
                    nome_arquivo_seguro(
                        nome
                    )
                    +
                    ".postman_collection.json"
                )

                destino = (
                    pasta_saida
                    /
                    nome_saida
                )

                salvar_json(
                    collection,
                    destino
                )

                quantidade += 1

                self.escrever_log(
                    f"OK: {destino.name}"
                )

            except Exception as erro:

                erros += 1

                self.escrever_log(
                    (
                        f"ERRO: "
                        f"{Path(caminho).name} "
                        f"→ {erro}"
                    )
                )

        messagebox.showinfo(
            "Conversão concluída",
            (
                f"Convertidos: {quantidade}\n"
                f"Erros: {erros}\n\n"
                f"Pasta:\n{pasta_saida}"
            )
        )


# ============================================================
# MAIN
# ============================================================

def main():

    root = tk.Tk()
    

    app = ConversorPostmanApp(
        root
    )

    root.mainloop()


if __name__ == "__main__":

    main()