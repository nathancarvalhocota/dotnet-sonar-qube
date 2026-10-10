# dotnet-sonar-qube

Skill para **Claude Code, Codex e agentes compatíveis com Agent Skills** que executa `SonarAnalyzer.CSharp` localmente e reporta diagnósticos nas linhas C# alteradas da branch.

Compara o estado atual com o merge base da referência escolhida, incluindo commits, alterações staged/unstaged e arquivos não rastreados. Compila com o analisador, filtra as ocorrências e orienta o agente a avaliar cada uma sem corrigir o código automaticamente.

## Escopo e requisitos

- Projetos **C#/.NET** compiláveis com `dotnet build`; esta implementação não inclui analisadores para VB.NET, F#, JavaScript ou outras linguagens.
- Git, Python **3.10+** (somente biblioteca padrão) e o SDK .NET exigido pelo projeto. Funciona por CLI em Windows, Linux e macOS, sem depender de Bash, `cygpath` ou IDE.
- Rede para baixar `SonarAnalyzer.CSharp` do NuGet no primeiro uso e para restaurar as dependências do projeto, quando necessário.
- Node.js/npm apenas se optar pela instalação com `npx skills`.

O analisador tem a versão fixada em [analyzer/VERSION](analyzer/VERSION), inicialmente `10.34.0.3385`, preservando a versão da skill original. As DLLs e o pacote são baixados para a pasta da skill e não são distribuídos neste repositório. Atualizar a skill não atualiza automaticamente o analisador para a última versão do NuGet.

A skill usa o [analisador Roslyn da SonarSource](https://www.nuget.org/packages/SonarAnalyzer.CSharp/10.34.0.3385), sem precisar de servidor SonarQube, token ou envio de código. Ela não executa SonarScanner, não sincroniza quality profiles e não produz quality gates ou a análise completa do SonarQube Server/Cloud. As regras habilitadas dependem do analisador e da configuração local do projeto.

## Instalação

```sh
# Claude Code
npx skills add nathancarvalhocota/dotnet-sonar-qube -g -a claude-code

# Codex
npx skills add nathancarvalhocota/dotnet-sonar-qube -g -a codex

# Ambos
npx skills add nathancarvalhocota/dotnet-sonar-qube -g -a claude-code -a codex
```

Para instalar apenas no projeto atual, execute na raiz dele e omita `-g`. O CLI usa `.agents/skills` para o Codex e cria a instalação do Claude em `.claude/skills`. Por padrão, pode criar links para uma cópia compartilhada; `--copy` solicita cópias independentes.

Também é possível clonar manualmente. Escolha um destino global:

```sh
# Claude Code
git clone https://github.com/nathancarvalhocota/dotnet-sonar-qube.git "$HOME/.claude/skills/dotnet-sonar-qube"

# Codex e outros agentes que leem .agents/skills
git clone https://github.com/nathancarvalhocota/dotnet-sonar-qube.git "$HOME/.agents/skills/dotnet-sonar-qube"
```

Para instalação somente no projeto, use `.claude/skills/dotnet-sonar-qube` ou `.agents/skills/dotnet-sonar-qube`, relativos à raiz do projeto. Outros agentes precisam reconhecer o formato `SKILL.md` e o caminho escolhido.

Em ambientes que carregam skills de `$CODEX_HOME/skills`, você também pode clonar em `~/.codex/skills/dotnet-sonar-qube` (ou no `CODEX_HOME` personalizado). Para novas instalações compartilhadas, prefira `.agents/skills`, conforme a [documentação atual do Codex](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills). Mantenha um único destino por agente para evitar duplicatas.

Os comandos com `$HOME` funcionam em Bash, Git Bash e PowerShell. No Windows, a pasta do usuário costuma ser `C:\Users\<usuario>`. Preserve toda a pasta da skill, incluindo `scripts`, `agents`, `analyzer/VERSION` e `sonar.targets`.

## Uso nos agentes

Claude Code:

```text
/dotnet-sonar-qube main
```

Codex:

```text
$dotnet-sonar-qube analise as linhas alteradas em relação a main
```

Outros agentes: peça para carregar `dotnet-sonar-qube` e analisar a branch, ou informe o caminho de `SKILL.md` quando o agente não oferecer descoberta automática. Se necessário, reinicie a sessão para reconhecer a instalação.

A execução permanece **sob demanda**: `disable-model-invocation: true` no Claude e `allow_implicit_invocation: false` em `agents/openai.yaml` no Codex. Não é necessário adicionar uma instrução automática ao `CLAUDE.md` ou `AGENTS.md`. Em agentes que não reconhecem essas opções, as instruções da skill também limitam a execução aos pedidos de análise.

## Uso direto por CLI

Na raiz Git do projeto que será analisado, substitua `<skill_dir>` pela pasta instalada. Em Windows, troque `python3` por `py -3` ou pelo comando Python disponível.

```sh
# Conferir os intervalos, sem baixar o analisador nem compilar
python3 "<skill_dir>/scripts/analyze.py" ranges --base main

# Baixar o analisador fixado, sem compilar
python3 "<skill_dir>/scripts/analyze.py" setup

# Compilar e analisar as linhas alteradas
python3 "<skill_dir>/scripts/analyze.py" run --base main

# Escolher alvo, excluir arquivos e silenciar regras explicitamente
python3 "<skill_dir>/scripts/analyze.py" run --base origin/main --target FinanceBot.sln --exclude 'src/Clients/**' --ignore-rule S1135 --ignore-rule S1125
```

`--repo <pasta>` seleciona outro repositório; `--target` é relativo à raiz Git dele. `--exclude` aceita pathspecs Git e pode ser repetido. Arquivos `*.Designer.cs` são excluídos por padrão; nenhuma regra Sonar é silenciada por padrão.

O comando `run` usa `dotnet build --no-incremental --no-restore` e injeta [sonar.targets](sonar.targets) via `CustomBeforeMicrosoftCommonTargets`, habilitando os analisadores no build. Ele não adiciona `PackageReference` nem edita arquivos de configuração do projeto. Faça `dotnet restore` quando as dependências ainda não estiverem restauradas. O próprio build pode executar tarefas customizadas e gerar arquivos; confira o estado Git depois.

O resultado é JSON e contém `status`, `findings`, contagens e a pasta temporária de artefatos (`ranges.json`, `build.log`, `result.json`). Sem linhas elegíveis, retorna `no_changed_lines` e não baixa nem compila. Build com falha retorna `build_failed` e código de saída 1; diagnóstico incompleto não deve ser apresentado como análise limpa.

Para filtrar novamente um log existente:

```sh
python3 "<skill_dir>/scripts/analyze.py" filter "<artefatos>/build.log" "<artefatos>/ranges.json"
```

As ocorrências são deduplicadas por arquivo, linha, regra e mensagem. `.razor` entra nos intervalos, mas só aparece no relatório se o build emitir um diagnóstico Sonar mapeado ao arquivo original. Código gerado, regras desabilitadas, diagnósticos sem localização e arquivos fora do alvo compilado limitam a cobertura. A flag `git_status_changed` compara o status antes e depois do build; não detecta toda alteração de conteúdo em arquivos que já estavam modificados.

## Migração da skill `sonar-qube`

A skill antiga usava o comando `/sonar-qube`, caminhos fixos de `.claude`, Bash e preferências de um projeto específico. A nova se chama `dotnet-sonar-qube`, usa Python e resolve seus recursos pela própria pasta.

Instale e valide a nova antes de remover a pasta antiga `~/.claude/skills/sonar-qube`. Se você usa as exclusões `src/Clients/**` ou as regras silenciadas `S1135`/`S1125`, passe-as explicitamente ou registre a preferência nas convenções do seu projeto. Esta instalação não remove nem modifica a skill antiga automaticamente.

## Atualizar e remover

```sh
npx skills update dotnet-sonar-qube -g
npx skills remove dotnet-sonar-qube -g
```

Para instalação por projeto, use `npx skills update dotnet-sonar-qube -p` e `npx skills remove dotnet-sonar-qube` na raiz dele. Se clonou manualmente, atualize com `git -C <pasta-da-skill> pull --ff-only`; para remover, exclua essa pasta.

Se você adicionou uma instrução sobre a skill a um `CLAUDE.md`, `AGENTS.md` ou arquivo equivalente, remova-a ao desinstalar no escopo correspondente. Preserve instruções compartilhadas com agentes que continuam usando a skill.

## Desenvolvimento e referências

```sh
python3 -m unittest discover -s tests -v
```

Para testar também um build real, com SDK .NET 8 e acesso ao NuGet, execute `python3 tests/smoke_build.py`. O teste cria um repositório temporário, verifica um aviso novo versus um preexistente e confirma o tratamento de falha de compilação; ele não usa o projeto em que você trabalha.

- [Skills no Claude Code](https://code.claude.com/docs/en/skills)
- [Skills no Codex](https://learn.chatgpt.com/docs/build-skills)
- [CLI `skills`](https://github.com/vercel-labs/skills)
- [SonarSource/sonar-dotnet](https://github.com/SonarSource/sonar-dotnet)

Este projeto é uma integração independente; o analisador baixado mantém a licença e os termos publicados pela SonarSource no pacote NuGet.
