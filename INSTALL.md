# Instalação

O fluxo `cp` / `ln -s` foi **deprecado**.

Instale o plugin a partir deste repositório (Claude Code, Copilot CLI, Cursor)
conforme as seções de instalação em **[README.md](README.md)**.

Pré-requisito: `@playwright/cli` (skill oficial `playwright-cli`).

Verificação real da instalação (na raiz do plugin):

```bash
npm test
```

Distinção: política ≠ permissão do servidor ≠ proteção do host. Sem
`--policy` o perfil é legado. Self-tests: README → *Self-tests dos gates*.
Corpus de evals fica fora da job de PR.
