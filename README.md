# 📖 MangaKoro

O **MangaKoro** é um leitor desktop de mangás moderno, rápido e elegante, totalmente integrado à API v5 do MangaDex. Desenvolvido em Python 3.10+ com PyQt6, ele foi projetado para oferecer a melhor experiência de leitura diretamente no seu computador, com foco em desempenho e usabilidade.

---

##  Funcionalidades Principais

* **Interface Moderna:** Design limpo com temas escuros amigáveis aos olhos e ícones nativos de alta qualidade.
* **Busca Inteligente:** Motor de busca integrado com filtros avançados por idioma, status da obra e tags (gêneros).
* **Leitor Altamente Customizável:** Adapte a leitura ao seu estilo com opções de rolagem vertical, página única ou dupla, controle de zoom e cores de fundo ajustáveis.
* **Biblioteca Pessoal:** Sistema robusto de favoritos e histórico de leitura armazenados localmente para garantir sua privacidade.

---

##  Como Instalar e Executar

###  Pré-requisitos
* Python 3.10 ou superior instalado no seu sistema.

Escolha o seu sistema operacional abaixo e siga os comandos no terminal:

###  Windows (PowerShell)
```powershell
# 1. Clone o repositório ou navegue até a pasta do projeto
cd caminho\para\MangaKoro

# 2. Crie e ative o ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Instale as dependências necessárias
pip install -r requirements.txt

# 4. Inicie o aplicativo
python main.py
```

### Linux (Terminal)
```terminal
# 1. Navegue até a pasta do projeto
cd caminho/para/MangaKoro

# 2. Crie e ative o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Instale as dependências necessárias
pip install -r requirements.txt

# 4. Inicie o aplicativo
python3 main.py
```

### macOS (Terminal)
```terminal
# 1. Navegue até a pasta do projeto
cd caminho/para/MangaKoro

# 2. Crie e ative o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Instale as dependências necessárias
pip install -r requirements.txt

# 4. Inicie o aplicativo
python3 main.py
```

# Armazenamento de Dados
Para garantir a sua privacidade e um carregamento rápido, o MangaKoro opera de forma offline-first para as suas preferências.

Nota de Privacidade: Todos os seus dados de salvamento, histórico de leitura, cache de imagens e configurações gerais ficam armazenados localmente e de forma segura na pasta pessoal de cada usuário, dentro do diretório `.mangalume`. No Windows, o caminho é `%USERPROFILE%\\.mangalume`; no Linux e macOS, `~/.mangalume`.

🛠️ Tecnologias Utilizadas
* [Python 3.10+](https://www.python.org/)
* [PyQt6 (Interface Gráfica)](https://pypi.org/project/PyQt6/)
* [Requests (Integração com API)](https://pypi.org/project/requests/)
* [QtAwesome (Gerenciamento de Ícones)](https://pypi.org/project/QtAwesome/)
* [Junte-se ao nosso Discord](https://discord.gg/xTHuFMCSbt)

