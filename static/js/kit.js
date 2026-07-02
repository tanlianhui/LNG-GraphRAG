/* ============================================================
   LNG UI Kit — Toast + Dialog (vanilla, no deps)
   Public API (also the contract for the React ports, see KIT_SPEC.md):
     toast.success(msg, opts)   toast.error(msg, opts)   toast.info(msg, opts)
     confirmDialog({ title, message, confirmText, cancelText, danger }) -> Promise<boolean>
   ============================================================ */
(function () {
    "use strict";

    // ---------- Toast ----------
    function ensureWrap() {
        let wrap = document.querySelector(".kit-toast-wrap");
        if (!wrap) {
            wrap = document.createElement("div");
            wrap.className = "kit-toast-wrap";
            wrap.setAttribute("role", "status");
            wrap.setAttribute("aria-live", "polite");
            document.body.appendChild(wrap);
        }
        return wrap;
    }

    const ICONS = { success: "✓", error: "✕", info: "ℹ" };

    function showToast(type, msg, opts) {
        opts = opts || {};
        const duration = opts.duration == null ? 3800 : opts.duration;
        const wrap = ensureWrap();

        const el = document.createElement("div");
        el.className = "kit-toast " + type;

        const icon = document.createElement("span");
        icon.className = "kit-toast-icon";
        icon.textContent = ICONS[type] || ICONS.info;

        const body = document.createElement("span");
        body.className = "kit-toast-msg";
        body.textContent = msg;

        const close = document.createElement("button");
        close.className = "kit-toast-close";
        close.setAttribute("aria-label", "Dismiss");
        close.textContent = "×";

        el.append(icon, body, close);
        wrap.appendChild(el);

        let timer;
        const remove = () => {
            if (el.classList.contains("leaving")) return;
            el.classList.add("leaving");
            clearTimeout(timer);
            el.addEventListener("animationend", () => el.remove(), { once: true });
            setTimeout(() => el.remove(), 250); // fallback
        };
        close.addEventListener("click", remove);
        if (duration > 0) timer = setTimeout(remove, duration);
        return remove;
    }

    const toast = {
        success: (m, o) => showToast("success", m, o),
        error: (m, o) => showToast("error", m, o),
        info: (m, o) => showToast("info", m, o),
    };

    // ---------- Confirm dialog ----------
    function confirmDialog(opts) {
        opts = opts || {};
        const title = opts.title || "Are you sure?";
        const message = opts.message || "";
        const confirmText = opts.confirmText || "Confirm";
        const cancelText = opts.cancelText || "Cancel";
        const danger = !!opts.danger;

        return new Promise((resolve) => {
            const backdrop = document.createElement("div");
            backdrop.className = "kit-dialog-backdrop";

            const dialog = document.createElement("div");
            dialog.className = "kit-dialog";
            dialog.setAttribute("role", "dialog");
            dialog.setAttribute("aria-modal", "true");

            const h = document.createElement("h3");
            h.textContent = title;
            const p = document.createElement("p");
            p.textContent = message;

            const actions = document.createElement("div");
            actions.className = "kit-dialog-actions";

            const cancelBtn = document.createElement("button");
            cancelBtn.className = "kit-btn kit-btn-ghost";
            cancelBtn.textContent = cancelText;

            const okBtn = document.createElement("button");
            okBtn.className = "kit-btn " + (danger ? "kit-btn-danger" : "kit-btn-primary");
            okBtn.textContent = confirmText;

            actions.append(cancelBtn, okBtn);
            dialog.append(h);
            if (message) dialog.append(p);
            dialog.append(actions);
            backdrop.append(dialog);
            document.body.append(backdrop);

            const prevFocus = document.activeElement;
            okBtn.focus();

            function done(result) {
                document.removeEventListener("keydown", onKey);
                backdrop.remove();
                if (prevFocus && prevFocus.focus) prevFocus.focus();
                resolve(result);
            }
            function onKey(e) {
                if (e.key === "Escape") done(false);
                if (e.key === "Enter") done(true);
            }
            cancelBtn.addEventListener("click", () => done(false));
            okBtn.addEventListener("click", () => done(true));
            backdrop.addEventListener("click", (e) => { if (e.target === backdrop) done(false); });
            document.addEventListener("keydown", onKey);
        });
    }

    window.toast = toast;
    window.confirmDialog = confirmDialog;
})();
