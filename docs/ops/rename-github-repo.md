# Git remote sync

GitHub repo is **Brohammad/VoxForge** (renamed from `VoxFauge`). GitHub redirects old clone URLs.

If your local `origin` still points at `VoxFauge`:

```bash
git remote set-url origin https://github.com/Brohammad/VoxForge.git
git remote -v
```

Verify:

```bash
gh repo view Brohammad/VoxForge --json name,url
```
