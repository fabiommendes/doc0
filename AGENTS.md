# Instruções para agentes do doc-zero

`doc-zero` é um gerador de documentação sem configuração para projetos Python. Ele analisa o `pyproject.toml` e a árvore de código do projeto. Depois, gera e controla um projeto Sphinx em `<root>/docs`. Veja o README.md para a apresentação voltada ao usuário.

## Idioma

Nível 2 (aplicativo público), conforme `~/git/tools/tooling-root/dev/adr/0002-idioma-dos-repositorios.md`:

- Em inglês: código, comentários, docstrings, mensagens da CLI e de erro,
  `README.md`, a documentação de usuário em `docs/`, `CHANGELOG.md`,
  `CONTRIBUTING.md`, `ROADMAP.md`, `GLOSSARY.md` e mensagens de commit.
- Em português (pt-BR): este arquivo, `BACKLOG.md`, tudo em `dev/`, as ADRs e
  as issues.

## Configuração do ambiente

Requer Python >= 3.13. O código usa PEP 695 (genéricos e instruções `type`, por exemplo `def get[T](...)` e `type TomlValue = ...`). Esses trechos dão erro de sintaxe em interpretadores 3.12 e anteriores.

```bash
uv sync --all-groups   # installs runtime deps + the dev group (ruff, pytest, pytest-cov)
```

## Comandos comuns

Todos definidos como tarefas taskipy em `pyproject.toml`. Rode com `uv run task <nome>`.

| Tarefa       | Comando                                             | Finalidade                         |
| ------------ | --------------------------------------------------- | ---------------------------------- |
| `test`       | `pytest tests`                                      | Roda a suíte de testes             |
| `coverage`   | `pytest tests --cov=doc0 --cov-report=term-missing` | Roda os testes com relatório de cobertura |
| `lint`       | `ruff check .`                                      | Lint                               |
| `docs`       | `sphinx-build -b html docs/source docs/build -n`    | Gera a documentação do próprio doc-zero |
| `docs-serve` | `sphinx-autobuild docs/source docs/build -n`        | Servidor de documentação com recarga automática |
| `build`      | `uv build`                                          | Gera o pacote distribuível         |
| `release`    | lint + test + docs + build + tag                    | Fluxo completo de publicação       |

O CI (`.github/workflows/ci.yml`) roda `lint` e `coverage` em cada push e PR. Uma mudança não está pronta enquanto os dois não passarem localmente.

## Layout do código-fonte

- `doc0/base.py`: `Doc0` (o ponto de entrada principal: `load`/`init`/`generate`/`build`/`serve`/`test`), além de `Conf`, `Index` e os auxiliares de renderização que eles usam. `generate()` é a etapa pura: lê as entradas do projeto (pyproject, README, LICENSE, entradas do diataxis, módulos de código-fonte) e retorna um `doc0.tree.DocTree` que descreve a árvore inteira da documentação como dados, sem escrever nada. `init()` é apenas `self.generate().write()`.
- `doc0/tree.py`: `DocTree`/`DocFile`/`WritePolicy`: a árvore de documentação como dados (caminho absoluto -> conteúdo + política `OVERWRITE`/`IF_MISSING`) e o único lugar que toca o disco para gravá-la (`DocTree.write()`). Inclui a limpeza de `owned_dirs` (por exemplo, `docs/api`), para que os arquivos gerados antigos desapareçam.
- `doc0/pyproject.py`: `PyProject` analisa o `pyproject.toml` e resolve o layout do projeto para encontrar os módulos raiz. `find_root_modules()` deriva uma vez os fatos compartilhados (`_ProjectFacts`: nome normalizado, build backend, configuração do uv). Depois tenta `uv_build` -> `src` -> `toplevel`, nessa ordem. Cada `_resolve_*_layout` retorna os módulos raiz ou levanta `_LayoutInapplicable` com um motivo. Se nenhum se aplicar, um único `RuntimeError` lista todos os motivos. Adicione novos layouts ali, não como pares separados de detector e finder.
- `doc0/module.py`: `ModuleSpec` (localiza e carrega um módulo do disco) e `Module` (a docstring, as exportações e a renderização de um módulo carregado). `Module.render()` usa `doc0/exports.py` para escolher entre uma listagem ordenada e dividida em seções, ou o fallback simples `automodule`. `find_public_modules(roots)` (interna, não reexportada) é o único lugar que decide quais módulos são documentados e em que ordem. Primeiro vêm as raízes, sempre. Depois vêm os submódulos com docstring e cujo nome não começa com `_`, em ordem de `iter_submodules()`, com aviso sobre `__all__` ausente ou vazio. `Doc0.generate()` apenas consome o resultado dela.
- `doc0/exports.py`: interna (não reexportada). Faz a análise estática do literal `__all__` de um módulo, via `ast` e `tokenize`. Transforma esse literal em seções ordenadas, delimitadas por `#:`, com texto opcional de vários parágrafos. Isso só acontece quando dá para fazer com segurança. Veja a docstring do módulo para as regras exatas e uma limitação documentada de casos extremos. Retorna `None` para qualquer coisa dinâmica, calculada ou que não bata com o `__all__` em tempo de execução. Para módulos sem `__all__`, `parse_reexport_sections` lista as reexportações explícitas (`from x import y as y`) e as definições e classes públicas, na ordem do código-fonte. Isso é usado em pacotes no estilo do typer. Retorna `None` se não houver reexportações.
- `doc0/theme.py`: interna. `resolve_theme(cli_theme, pyproject)` é o único lugar que decide o tema do Sphinx. A precedência é `--theme`, depois `[tool.doc-zero] theme`, depois `"default"`. Em seguida vêm a validação e a expansão de aliases (`rtd`/`readthedocs` -> `sphinx_rtd_theme`, `default` -> `alabaster`). `Doc0.load` chama essa função, então `Doc0.theme` sempre guarda o nome resolvido do Sphinx. Valores inválidos levantam `ThemeError` (um `ValueError`) com o nome da origem do valor. A CLI transforma isso em erro de uso (saída 2).
- `doc0/readme.py`: interna. `readme_body(src)` transforma o README.md na página inicial da documentação (`_readme.md`). Depois de um marcador `<!-- doc-zero-start -->` (ou o legado `<!-- doc0-start -->`), o restante é mantido sem alterações. Caso contrário, são removidas as linhas que contêm só badges (de hosts conhecidos em `BADGE_HOSTS`, ou com "badge" no caminho da URL da imagem), as definições de link órfãs delas e o título inicial. Badges no meio de um texto e dentro de blocos de código são mantidos. Nos dois modos, um marcador `<!-- doc-zero-end -->` (ou `<!-- doc0-end -->`) se remove e remove tudo o que vem depois dele.
- `doc0/util.py`: pequenos auxiliares independentes (`validate_theme`, `first_existing`).
- `doc0/cli.py`: o script de console `doc0`, feito com Typer (`app.command()` para `build`/`serve`/`test`).
- `doc0/__init__.py`: a superfície pública do pacote: `Doc0`, `Module`, `ModuleSpec`, `PyProject`. Tudo que não é reexportado aqui é interno, mesmo que não comece com `_` (por exemplo, `Conf` e `Index` em `base.py`).

## Convenções de testes

Os testes ficam em `tests/` e são **baseados em cenários e só usam a API pública**. Veja a docstring do módulo em `tests/conftest.py` para o raciocínio completo. Em resumo:

- Exercite tudo pelos pontos de entrada públicos do `doc0` (`Doc0.load()` e seus métodos, `PyProject`, `ModuleSpec`/`Module`, `validate_theme`, a CLI via `typer.testing.CliRunner`). Não teste diretamente métodos privados (prefixados com `_`). Exercite-os indiretamente, em um cenário realista.
- Crie projetos de teste no disco com os auxiliares de `tests/conftest.py` (`make_pyproject_toml`, `make_package`, `make_module_file`, `write`), em vez de simular os internos do doc-zero.
- `Doc0.build()`/`serve()` importam Sphinx e sphinx-autobuild sob demanda. A fixture `fake_sphinx` faz stub dessas importações via `sys.modules`, para que os testes não precisem das dependências pesadas instaladas.
- O corpus sempre verde (`tests/test_corpus.py`, manifesto em `tests/corpus/corpus.toml`) roda builds reais do Sphinx. Os projetos locais em `tests/corpus/<nome>/` são construídos a cada execução e devem gerar exatamente as páginas de API listadas. Projetos externos são clonados e construídos no próprio virtualenv somente com `pytest -m slow` (o workflow `corpus` do CI). A lista de páginas deles é um subconjunto, então mudanças no upstream não quebram o build. Quando um projeto real quebrar o doc0, adicione um projeto local com o mesmo formato.
- Quando um teste revelar um bug real, prefira corrigir o bug a ajustar o teste ao comportamento errado. Se a correção estiver fora do escopo da mudança atual, escreva o teste como um teste de caracterização explícito. Adicione uma docstring explicando o bug que ele documenta. Não valide a saída errada em silêncio. Mantenha essas docstrings em dia quando o bug for corrigido depois: um teste de caracterização cuja docstring ainda descreve um bug já corrigido induz a erro.

Busque cobertura próxima de 100% em `doc0/`. Lacunas devem ser código defensivo genuinamente inalcançável (diga isso explicitamente) ou um sinal de que um caminho público precisa de um novo cenário.

## Fluxo agêntico e caminhos

O diretório `prompts/` contém modelos de prompt reutilizáveis para agentes de código.

O diretório `dev/` é um rastreador de issues:
- `dev/issues/*.md`: arquivos individuais de issue, em Markdown.
- `dev/spec/to-do/*.md`: arquivos de especificação para tarefas que precisam ser feitas.
- `dev/spec/to-review/*.md`: arquivos de especificação para tarefas concluídas. São removidos após a revisão.

### Glossário

Leia sempre a lista de definições do glossário com:

```bash
 grep -oP "^## \K.+" GLOSSARY.md
```

Para ver os detalhes de uma definição, use:

```bash
awk  'BEGIN { IGNORECASE = 1 } /## <TERM>/{flag=1; next} /##/{flag=0} flag' GLOSSARY.md
```

Substitua <TERM> pelo termo que você quer consultar.

Se uma conversa introduzir um conceito ou uma palavra novos, pergunte ao humano se eles devem entrar no glossário. Ao adicionar entradas, seja extremamente sucinto. Adicione-as em ordem alfabética.


## Convenções de código

- Python 3.13+, `from __future__ import annotations` no topo dos módulos que precisam dele para referências adiantadas.
- Dataclasses em vez de classes comuns para tipos que carregam dados.
- Prefira tipagem precisa (genéricos PEP 695, `TypedDict`, `Annotated`). Este projeto roda `mypy --strict` (veja `[tool.mypy]` em `pyproject.toml`).
- Siga o `ruff check .`. Não há configuração de formatador além dos padrões do ruff.
- Evite sombrear builtins com nomes de parâmetros (por exemplo, `type`, `id`, `list`) dentro de uma função que também precisa do builtin. Este código já caiu nisso uma vez (veja o histórico do git em volta de `PyProject.get()`).

## Pontos fracos conhecidos

Mantenha esta seção atualizada. Atualize-a sempre que um problema parecido for encontrado ou corrigido, para que continue sendo um mapa confiável, e não uma lista de curiosidades desatualizadas.

- `Index`/`Conf` (em `base.py`) e outros nomes sem `_` que não aparecem em `doc0/__init__.py.__all__` são internos. Mas nada impede isso na importação. Não aumente a API pública por acidente: se algo precisar se tornar público, adicione-o a `__all__` de forma deliberada.
- A resolução de layout (`doc0/pyproject.py`) segue as regras do uv: o nome normalizado vira minúsculo, com `-`/`.` trocados por `_`, mesmo no layout `toplevel`. Por isso, um diretório de pacote com maiúsculas e minúsculas misturadas, como `Acme/`, não é encontrado. Pacotes stub do uv (`foo-stubs` -> `foo-stubs/`) não são tratados. Um `module-root` que não é string volta para `"src"` sem aviso.
- O carregamento de módulos (`ModuleSpec.load_module()`) importa os módulos da forma normal (`importlib.import_module`), depois de colocar em primeiro lugar no `sys.path` o diretório que contém o pacote de topo. Um módulo que já está em `sys.modules` é reaproveitado. Assim, se uma cópia com o mesmo nome foi importada antes (por exemplo, o doc0 documentando a si mesmo), essa cópia é documentada no lugar da árvore de código-fonte. Os testes dependem da fixture `isolated_imports` (autouse) em `tests/conftest.py` para remover os pacotes de fixture entre um teste e outro.
