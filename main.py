'''
Organize Files - Tool for organizing and separating files.
Copyright (C) 2024 CleitinhoDEV

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

---

Organize Files - Ferramenta separar arquivos de forma organizada.
Copyright (C) 2024 CleitinhoDEV

Este programa é um software livre: você pode redistribuí-lo e/ou modificá-lo
sob os termos da Licença Pública Geral GNU, conforme publicada pela
Free Software Foundation, na versão 3 da Licença, ou (a seu critério) qualquer versão posterior.

Este programa é distribuído na esperança de que seja útil,
mas SEM QUALQUER GARANTIA; sem mesmo a garantia implícita de
COMERCIABILIDADE ou ADEQUAÇÃO A UM DETERMINADO PROPÓSITO. Consulte a
Licença Pública Geral GNU para mais detalhes.

Você deve ter recebido uma cópia da Licença Pública Geral GNU
junto com este programa. Caso contrário, veja <https://www.gnu.org/licenses/>.
'''

import os
import shutil
import customtkinter as ctk
from tkinter import filedialog
from datetime import datetime
import threading
import webbrowser


# Função para selecionar a pasta
def selecionar_pasta():
    pasta = filedialog.askdirectory()  # Abre a janela de seleção de pasta
    return pasta


# Função para organizar os arquivos por tipo
def organizar_arquivos_tipo(pasta):
    # Contadores
    contador_arquivos = 0
    total_arquivos = len([f for f in os.listdir(pasta) if os.path.isfile(os.path.join(pasta, f))])

    for arquivo in os.listdir(pasta):
        caminho_arquivo = os.path.join(pasta, arquivo)
        if os.path.isfile(caminho_arquivo):
            _, extensao = os.path.splitext(arquivo)
            extensao = extensao.lower()[1:]
            if not extensao:
                continue
            pasta_destino = os.path.join(pasta, extensao.upper())
            if not os.path.exists(pasta_destino):
                os.makedirs(pasta_destino)
            novo_caminho = os.path.join(pasta_destino, arquivo)
            shutil.move(caminho_arquivo, novo_caminho)

            # Atualiza o contador
            contador_arquivos += 1

    # Exibe a quantidade de arquivos
    print(f"Total de arquivos: {total_arquivos}")
    print(f"Arquivos movidos: {contador_arquivos}")


# Função para organizar os arquivos por data (Mês/Ano)
def organizar_arquivos_data(pasta):
    # Contadores
    contador_arquivos = 0
    total_arquivos = len([f for f in os.listdir(pasta) if os.path.isfile(os.path.join(pasta, f))])

    for arquivo in os.listdir(pasta):
        caminho_arquivo = os.path.join(pasta, arquivo)
        if os.path.isfile(caminho_arquivo):
            # Pega a data de modificação do arquivo
            data_modificacao = os.path.getmtime(caminho_arquivo)  # Pega a data de modificação
            data_formatada = datetime.fromtimestamp(data_modificacao).strftime("%Y/%m")  # Ano/Mês

            # Cria a pasta de destino com o nome formatado
            pasta_destino = os.path.join(pasta, data_formatada)
            if not os.path.exists(pasta_destino):
                os.makedirs(pasta_destino)

            # Move o arquivo para a pasta correspondente
            novo_caminho = os.path.join(pasta_destino, arquivo)
            shutil.move(caminho_arquivo, novo_caminho)

            # Atualiza o contador
            contador_arquivos += 1

    # Exibe a quantidade de arquivos
    print(f"Total de arquivos: {total_arquivos}")
    print(f"Arquivos movidos: {contador_arquivos}")


# Função para organizar os arquivos por ordem alfabética (A, B, C, ...)
def organizar_arquivos_abc(pasta):
    # Contadores
    contador_arquivos = 0
    total_arquivos = len([f for f in os.listdir(pasta) if os.path.isfile(os.path.join(pasta, f))])

    for arquivo in os.listdir(pasta):
        caminho_arquivo = os.path.join(pasta, arquivo)
        if os.path.isfile(caminho_arquivo):
            # Obtém o primeiro caractere do nome do arquivo
            primeiro_caractere = arquivo[0].upper()

            if primeiro_caractere.isalpha():  # Se for uma letra
                pasta_destino = os.path.join(pasta, primeiro_caractere)  # Pastas por letras
            elif primeiro_caractere.isdigit():  # Se for um número
                pasta_destino = os.path.join(pasta, '0-9')  # Pastas para números (0-9)
            else:  # Se for um símbolo ou caractere especial
                pasta_destino = os.path.join(pasta, 'Outros')  # Pastas para símbolos ou caracteres especiais

            # Cria a pasta de destino se não existir
            if not os.path.exists(pasta_destino):
                os.makedirs(pasta_destino)

            # Move o arquivo para a pasta correspondente
            novo_caminho = os.path.join(pasta_destino, arquivo)
            shutil.move(caminho_arquivo, novo_caminho)

            # Atualiza o contador
            contador_arquivos += 1

    # Exibe a quantidade de arquivos
    print(f"Total de arquivos: {total_arquivos}")
    print(f"Arquivos movidos: {contador_arquivos}")


# Função chamada quando o botão "Organizar" é clicado
def organizar():
    pasta = caminho_var.get()
    if pasta == "" or pasta == "Selecione o caminho":
        resultado_label.configure(text="Erro: Nenhum caminho selecionado!", fg_color="red")
        return

    if tipo_var.get():
        organizar_arquivos_tipo(pasta)
        resultado_label.configure(text=f"Arquivos organizados!", fg_color="green")
    elif data_var.get():
        organizar_arquivos_data(pasta)
        resultado_label.configure(text=f"Arquivos organizados!", fg_color="green")
    elif abc_var.get():
        organizar_arquivos_abc(pasta)
        resultado_label.configure(text=f"Arquivos organizados!", fg_color="green")
    else:
        resultado_label.configure(text="Erro: Nenhuma opção selecionada!", fg_color="red")


# Função chamada quando o botão "Selecionar caminho" é clicado
def selecionar():
    pasta = selecionar_pasta()
    if pasta:
        caminho_var.set(pasta)


# Função para garantir que apenas uma caixa de seleção esteja marcada
def marcar_uma_vez(valor):
    tipo_var.set(False)
    data_var.set(False)
    abc_var.set(False)
    valor.set(True)


# Função para abrir o link
def abrir_link():
    url = "https://www.bugzinho.com/organizefiles-br"
    webbrowser.open(url)


# Criar a janela principal
root = ctk.CTk()

# Configurações da janela
root.title("Organize Files")
root.geometry("500x400")
root.resizable(False,False)

# Calculando a posição para centralizar a janela
screen_width = root.winfo_screenwidth()  # Largura da tela
screen_height = root.winfo_screenheight()  # Altura da tela
window_width = 500  # Largura da janela
window_height = 180  # Altura da janela

# Ícone
root.iconbitmap("Design/icone.ico")

position_top = int(screen_height / 2 - window_height / 2)
position_left = int(screen_width / 2 - window_width / 2)
root.geometry(f'{window_width}x{window_height}+{position_left}+{position_top}')

# Frame

borda_botoes = ctk.CTkFrame(
        root,
        corner_radius=10,
        border_width=2,
        border_color='Black',
        width=490,
        height=170,
        fg_color='#151515')
borda_botoes.place(x=5, y=5)

# Caixa de texto para mostrar o caminho
caminho_var = ctk.StringVar(value="Selecione o caminho")
caminho_entry = ctk.CTkEntry(root, textvariable=caminho_var, width=305,
                             placeholder_text="Selecione uma pasta", bg_color='#151515')
caminho_entry.place(x=50, y=30)

# Botão para selecionar o caminho
selecao_btn = ctk.CTkButton(root, text="Buscar", command=selecionar, width=85,
                            fg_color="#483d8b", hover_color="#2c226a", bg_color='#151515')
selecao_btn.place(x=365, y=30)

# Variáveis de seleção para os tipos de organização
tipo_var = ctk.BooleanVar()
data_var = ctk.BooleanVar()
abc_var = ctk.BooleanVar()

# Inicializa "Tipo" como selecionado
tipo_var.set(True)

# Caixa de seleção para tipo, data e abc
tipo_checkbox = ctk.CTkCheckBox(root, text="Tipo", variable=tipo_var, command=lambda: marcar_uma_vez(tipo_var),
                                fg_color="#483d8b", hover_color="#2c226a", bg_color='#151515')
data_checkbox = ctk.CTkCheckBox(root, text="Data", variable=data_var, command=lambda: marcar_uma_vez(data_var),
                                fg_color="#483d8b", hover_color="#2c226a", bg_color='#151515')
abc_checkbox = ctk.CTkCheckBox(root, text="ABC", variable=abc_var, command=lambda: marcar_uma_vez(abc_var),
                               fg_color="#483d8b", hover_color="#2c226a", bg_color='#151515')

# Colocando as caixas de seleção
tipo_checkbox.place(x=210, y=74)
data_checkbox.place(x=280, y=74)
abc_checkbox.place(x=350, y=74)

# Botão para organizar os arquivos
organizar_btn = ctk.CTkButton(root, text="Organizar", command=organizar,
                              fg_color="#483d8b", hover_color="#2c226a",
                              bg_color='#151515')
organizar_btn.place(x=50, y=70)

# Label para mostrar o resultado (sucesso ou erro)
resultado_label = ctk.CTkLabel(root, text="", width=350, height=40, fg_color="gray")
resultado_label.place(x=71, y=120)

# Botão de Ajuda
botao_help = ctk.CTkButton(root, text="?",
                           command=lambda: threading.Thread(target=abrir_link).start(),
                           fg_color="#483d8b", hover_color="#2c226a", width=30, bg_color='#151515')
botao_help.place(x=419, y=70)

# Inicia a aplicação
root.mainloop()










