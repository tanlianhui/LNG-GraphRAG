# Shared UI Kit — Visual Spec

One primitive set, copied into each repo (per decision: copy-in, not a published package).
Vanilla implementation lives here (`static/js/kit.js`, `static/css/kit.css`) and is the
reference contract for the React ports in lyrics-learner, beatframe, gym-my-butler, screenshot-meme-qa.

Goal: kill native `alert()/confirm()/prompt()`, add consistent feedback (toast), safe
destructive confirms (dialog), and no-jank loading (skeleton) — while each repo keeps its
own accent color.

---

## 1. Design tokens

Each repo declares the same **token names**, different **values**. Vanilla uses CSS vars
(`--kit-*`); React repos map the same names into `tailwind.config` `theme.extend.colors.kit`.

| Token | Role | lng (gold) | lyrics (violet) | beatframe (indigo) | gym (heat) | meme (sky) |
|---|---|---|---|---|---|---|
| `accent` | primary CTA | `#D39B05` | `#7c3aed` | `#5b4fff` | `#F9A01B` | `#0ea5e9` |
| `accent-bright` | hover/active | `#FEAE02` | `#a78bfa` | `#7d73ff` | `#98002E` | `#38bdf8` |
| `bg` | app background | `#1E1E1E` | `#0a0a14` | `#0a0a0f` | `#000000` | `#020617` |
| `panel` | card/dialog surface | `#2a2a2a` | `#14141f` | `#111` | `#0e0e0e` | `#0f172a` |
| `border` | hairlines | `#525252` | `#1e1e2e` | `#222` | `#98002E55` | `#1e293b` |
| `text` | body text | `#e0e0e0` | `#e8e8e8` | `#e0e0f0` | `#ffffff` | `#e2e8f0` |
| `muted` | secondary text | `#9a9a9a` | `#888` | `#666` | `#BA9653` | `#94a3b8` |
| `ok` | success | `#2f9e44` | (shared) | (shared) | (shared) | `#22c55e` |
| `err` | error/danger | `#e03131` | (shared) | (shared) | (shared) | `#ef4444` |

Shared scalars (all repos): radius `10px` (cards) / `8px` (controls) / `14px` (dialog),
shadow `0 8px 30px rgba(0,0,0,.45)`, motion `160–220ms` on `cubic-bezier(.16,1,.3,1)`.
All animations gated behind `@media (prefers-reduced-motion: reduce)`.

---

## 2. Components

### Toast
Transient feedback, bottom-right stack, auto-dismiss.

- Variants: `success` (✓ / ok), `error` (✕ / err), `info` (ℹ / accent).
- Anatomy: `[icon] [message] [× close]`, 3px left border = variant color.
- Behavior: enter slide-up+fade 220ms; auto-remove after 3.8s (0 = sticky); manual close;
  stack newest at bottom; `role=status` `aria-live=polite`.
- Max width `min(360px, 100vw−40px)`; wraps long text.

```
API (identical vanilla + React):
  toast.success(msg, { duration })
  toast.error(msg, { duration })
  toast.info(msg, { duration })   // duration ms; 0 = persist. returns dismiss()
```

### ConfirmDialog
Modal replacement for `confirm()`. **Never** used for anything non-blocking (that's toast).

- Anatomy: title (h3) · optional message (p) · actions right-aligned `[Cancel] [Confirm]`.
- `danger:true` → Confirm button uses `err` fill (delete flows); else `accent` fill.
- Behavior: backdrop fade; card pop 180ms; focus Confirm on open; `Esc`=cancel,
  `Enter`=confirm; click-outside=cancel; restore focus to opener on close; `aria-modal`.

```
API:  confirmDialog({ title, message, confirmText, cancelText, danger }) -> Promise<boolean>
React: <ConfirmDialog/> driven by a useConfirm() hook returning the same promise.
```

### Skeleton
Shimmer placeholder matching final content box; no layout shift on load.

- Primitives: `skel-text` (line), width modifiers `70/90%`, `skel-card` (block).
- Shimmer 1.3s linear gradient sweep; reduced-motion → static muted block.
- Rule: render the **same grid/list shape** as loaded state, swap items for skeletons.

### Button (React repos only — lng keeps existing `.btn-*`)
Variants `primary | ghost | danger`, sizes `sm | md`. Same radius/motion tokens.
Disabled = `opacity .5` + `cursor not-allowed`. Loading = spinner + label, keeps width.

### EmptyState
Centered: glyph/illustration · title · one line of help · optional CTA button.
Replaces bare "No X yet" text. Copy stays in the repo's language (gym = zh-TW).

---

## 3. Per-repo application map

| Repo | Replaces | Adds |
|---|---|---|
| **lng-graphrag** | `confirm` (delete chunk), 6× `alert` | toast on save/delete/quiz; skeletons on query/test *(next phase)* |
| **lyrics-learner** | `window.confirm` delete, `window.prompt` YT edit | inline edit, ConfirmDialog, toast, song-card skeletons |
| **beatframe** | 3× `alert` (bad URL/file) | inline field error + toast; ConfirmDialog on beatmap delete |
| **gym-my-butler** | `alert` on generate fail | inline error banner + toast; checklist skeletons; EmptyState (zh-TW) |
| **screenshot-meme-qa** | residual inline status text | toast; search-result + library skeletons |

---

## 4. Port checklist (vanilla → React)

1. Copy tokens into `tailwind.config.ts` `theme.extend.colors.kit` with the repo's values.
2. Port `Toast` as a context provider + `useToast()`; keep the `toast.success/error/info` shape.
3. Port `ConfirmDialog` as `<ConfirmProvider>` + `useConfirm()` returning `Promise<boolean>`.
4. Port `Skeleton`, `Button`, `EmptyState` as presentational components.
5. Delete every `alert/confirm/prompt` in the repo; wire to the kit.
6. Verify: no native dialogs remain (`grep -n "alert(|confirm(|prompt("`).

Status: vanilla reference **built** (lng). React port pending per-repo build.
