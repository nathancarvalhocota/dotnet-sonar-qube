# dotnet-sonar-qube

Skill para **Claude Code, Codex e agentes compatíveis com Agent Skills** que executa `SonarAnalyzer.CSharp` localmente e reporta diagnósticos nas linhas C# alteradas da branch.

Compara o estado atual com o merge base da referência escolhida, incluindo commits, alterações staged/unstaged e arquivos não rastreados. Compila com o analisador, filtra as ocorrências e orienta o agente a avaliar cada uma sem corrigir o código automaticamente.

## Escopo e requisitos

- Projetos **C#/.NET** compiláveis com `dotnet build`; esta implementação não inclui analisadores para VB.NET, F#, JavaScript ou outras linguagens.
- Git, Python **3.10+** (somente biblioteca padrão) e o SDK .NET exigido pelo projeto. Compatível com Windows, Linux e macOS, sem depender de Bash, `cygpath` ou IDE.
- Rede para baixar `SonarAnalyzer.CSharp` do NuGet no primeiro uso e para restaurar as dependências do projeto, quando necessário.
- Node.js/npm apenas se optar pela instalação com `npx skills`.

O analisador tem a versão fixada em [analyzer/VERSION](analyzer/VERSION), atualmente `10.34.0.3385`. As DLLs e o pacote são baixados para a pasta da skill e reutilizados nas análises seguintes. Atualizar a skill não atualiza automaticamente o analisador para a última versão do NuGet.

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

A execução é **sob demanda**: `disable-model-invocation: true` no Claude e `allow_implicit_invocation: false` em `agents/openai.yaml` no Codex. Não é necessário adicionar uma instrução automática ao `CLAUDE.md` ou `AGENTS.md`. Em agentes que não reconhecem essas opções, as instruções da skill também limitam a execução aos pedidos de análise.

## Como funciona com o agente

O agente identifica a referência base (por padrão, `main`) e a solução ou projeto a compilar. Se houver linhas C# elegíveis, prepara o analisador automaticamente, executa o build e avalia os avisos encontrados nessas linhas. Você pode indicar outra referência, o projeto, exclusões e regras a silenciar no próprio pedido ao agente.

O script interno cuida da coleta de intervalos, do download e da filtragem; o agente lê o código e as convenções do projeto para explicar os resultados. Arquivos `*.Designer.cs` são excluídos por padrão; nenhuma regra Sonar é silenciada por padrão.

O arquivo [sonar.targets](sonar.targets) carrega a DLL da pasta da skill apenas durante aquele build, sem adicionar dependências ao `.csproj`. O próprio build pode executar tarefas customizadas e gerar arquivos; o agente deve informar efeitos observados e falhas de compilação.

A análise cobre os diagnósticos emitidos pelo build nas linhas alteradas. `.razor` só aparece quando o compilador mapear o aviso Sonar ao arquivo original. Código gerado, regras desabilitadas e arquivos fora do alvo compilado limitam a cobertura.

## Atualizar e remover

```sh
npx skills update dotnet-sonar-qube -g
npx skills remove dotnet-sonar-qube -g
```

Após atualizar, inicie uma nova sessão do agente para carregar as instruções atualizadas.

Para instalação por projeto, use `npx skills update dotnet-sonar-qube -p` e `npx skills remove dotnet-sonar-qube` na raiz dele. Se clonou manualmente, atualize com `git -C <pasta-da-skill> pull --ff-only`; para remover, exclua essa pasta.

Se você adicionou uma instrução sobre a skill a um `CLAUDE.md`, `AGENTS.md` ou arquivo equivalente, remova-a ao desinstalar no escopo correspondente. Preserve instruções compartilhadas com agentes que continuam usando a skill.
