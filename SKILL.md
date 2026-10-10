---
name: dotnet-sonar-qube
description: Análise local de C#/.NET com SonarAnalyzer.CSharp nas linhas alteradas da branch, sob demanda, sem corrigir o código.
disable-model-invocation: true
---

# Sonar no código C# alterado

Execute quando o usuário pedir esta análise. Use o analisador Roslyn `SonarAnalyzer.CSharp` via `dotnet build`; reporte apenas diagnósticos nas linhas criadas ou modificadas desde o merge base, incluindo alterações locais e arquivos não rastreados. A execução é local, sem servidor, token ou envio de código ao SonarQube.

## Preparação

- Resolva `skill_dir` pela pasta deste `SKILL.md`, independentemente de estar em `.claude`, `.codex` ou `.agents`. Os scripts e `sonar.targets` são relativos a ela.
- Use Python 3.10+ (`python3` em Unix, `py -3` ou `python` no Windows), Git e o SDK .NET exigido pelo projeto. Bash e `cygpath` são dispensáveis.
- Trabalhe na raiz Git. A branch base padrão é `main`; use a referência indicada pelo usuário. Se só houver a referência remota, use `origin/main`. Se a base estiver ausente ou não tiver ancestral comum, explique o problema; não escolha outra base silenciosamente.
- Leia as instruções aplicáveis (`AGENTS.md`, `CLAUDE.md`) e as convenções indicadas por elas. Identifique a solução ou o projeto a compilar; passe `--target` se houver ambiguidade.

## Execução

1. Avise que a análise pode executar um build de alguns minutos e chame o auxiliar interno:

   ```sh
   python3 "<skill_dir>/scripts/analyze.py" --base main
   ```

   No Windows, use `py -3` ou o comando Python disponível. Opções: `--repo caminho/repositorio`, `--target caminho/Projeto.sln` (relativo à raiz Git), `--exclude 'src/Clients/**'` e `--ignore-rule S1135` (as duas últimas repetíveis). Escolha exclusões e regras silenciadas a partir do pedido ou das convenções documentadas do projeto. `S1135` e `S1125` não são silenciadas por padrão.

   O auxiliar retorna JSON e executa a coleta de intervalos, a preparação do analisador, o build e a filtragem. Com `status: no_changed_lines`, ele não baixa nem compila; informe que não há linhas C# elegíveis e encerre. Arquivos `*.Designer.cs` são excluídos por padrão; `.razor` é elegível para diagnósticos que o compilador mapear ao arquivo original.

   O primeiro uso baixa a versão fixada em `analyzer/VERSION` do NuGet para a pasta da skill. O build injeta `sonar.targets`, força recompilação e habilita os analisadores, sem adicionar referências ao projeto. Logs, intervalos e resultados ficam em uma pasta temporária cujo caminho aparece no JSON.

   - Dependências ausentes (`NETSDK1004`/assets): execute `dotnet restore` para o alvo e repita uma vez.
   - Arquivo travado: identifique o processo ou debug a interromper e informe ao usuário.
   - Outros erros de build ou download: reporte o erro e o log; uma análise incompleta não significa ausência de problemas.
   - O build pode executar tarefas do próprio projeto e alterar arquivos gerados. Confira o estado Git e relate efeitos observados. Não reverta alterações do usuário.

2. Avalie cada ocorrência de `findings` lendo o trecho real. Distinga aviso procedente, conflito com convenção (cite a regra local) e falso positivo (explique por quê). Classifique o impacto como BLOCKER, MAJOR ou MINOR, deixando claro que é uma avaliação sua. Se a linha veio de um commit da branch, identifique o commit quando possível; alterações não commitadas devem ser identificadas como locais.

## Resposta

Comece pela quantidade de avisos nas linhas alteradas e de arquivos afetados. Para cada aviso, indique `arquivo:linha`, regra, impacto e veredito em uma frase. Relate erros, limitações de cobertura e efeitos do build quando existirem. Zero avisos significa zero diagnósticos emitidos e elegíveis neste build, não uma auditoria completa.

Esta skill produz um relatório. Só corrija o código se o usuário também tiver autorizado correções.
