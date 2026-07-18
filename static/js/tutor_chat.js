"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const body = document.body;
    const root = document.documentElement;
    const textarea = document.getElementById("aiQuestion");
    const sendButton = document.getElementById("aiSendButton");
    const charCount = document.getElementById("aiCharCount");
    const composer = document.getElementById("aiComposer");
    const sidebar = document.getElementById("chatSidebar");
    const overlay = document.getElementById("chatSidebarOverlay");
    const openButton = document.getElementById("chatSidebarOpen");
    const closeButton = document.getElementById("chatSidebarClose");
    const chatScroll = document.getElementById("chatScroll");

    const hideGlobalLoader = () => {
        const loader = document.getElementById("pageLoader");
        loader?.classList.add("hidden");
        loader?.setAttribute("aria-hidden", "true");
        body.classList.remove("easy-transition-loading");
    };

    const syncViewport = () => {
        const viewport = window.visualViewport;
        const height = Math.round(viewport?.height || window.innerHeight);
        const top = Math.round(viewport?.offsetTop || 0);
        root.style.setProperty("--ec-vh", `${height}px`);
        root.style.setProperty("--ec-top", `${top}px`);
        body.style.height = `${height}px`;
    };

    const scrollToBottom = (behavior = "auto") => {
        if (!chatScroll) return;
        chatScroll.scrollTo({ top: chatScroll.scrollHeight, behavior });
    };

    const updateComposer = () => {
        if (!textarea) return;
        textarea.style.height = "auto";
        textarea.style.height = `${Math.min(textarea.scrollHeight, 150)}px`;
        const length = textarea.value.length;
        if (charCount) charCount.textContent = `${length} / 1500`;
        if (sendButton) sendButton.disabled = textarea.value.trim().length === 0;
    };

    const openSidebar = () => {
        sidebar?.classList.add("is-open");
        overlay?.classList.add("is-visible");
        body.classList.add("ec-sidebar-open");
    };

    const closeSidebar = () => {
        sidebar?.classList.remove("is-open");
        overlay?.classList.remove("is-visible");
        body.classList.remove("ec-sidebar-open");
    };

    hideGlobalLoader();
    syncViewport();
    updateComposer();
    requestAnimationFrame(() => scrollToBottom());

    window.addEventListener("pageshow", hideGlobalLoader);
    window.addEventListener("resize", syncViewport, { passive: true });
    window.visualViewport?.addEventListener("resize", () => {
        syncViewport();
        requestAnimationFrame(() => scrollToBottom());
    });
    window.visualViewport?.addEventListener("scroll", syncViewport, { passive: true });

    textarea?.addEventListener("input", updateComposer);
    textarea?.addEventListener("focus", () => {
        window.setTimeout(() => {
            syncViewport();
            scrollToBottom("smooth");
        }, 120);
    });
    textarea?.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            if (textarea.value.trim()) composer?.requestSubmit();
        }
    });

    openButton?.addEventListener("click", openSidebar);
    closeButton?.addEventListener("click", closeSidebar);
    overlay?.addEventListener("click", closeSidebar);
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeSidebar();
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
            event.preventDefault();
            window.location.assign(composer?.action || window.location.pathname);
        }
    });

    document.querySelectorAll("[data-copy-answer]").forEach((button) => {
        button.addEventListener("click", async () => {
            const answer = button.closest(".ec-assistant-body")?.querySelector(".ai-answer-text")?.textContent?.trim();
            if (!answer) return;
            try {
                await navigator.clipboard.writeText(answer);
                const label = button.querySelector("span");
                if (label) label.textContent = "Скопійовано";
                button.classList.add("is-copied");
                window.setTimeout(() => {
                    if (label) label.textContent = "Копіювати";
                    button.classList.remove("is-copied");
                }, 1400);
            } catch (error) {
                button.title = "Не вдалося скопіювати";
            }
        });
    });

    composer?.addEventListener("submit", (event) => {
        if (!textarea?.value.trim()) {
            event.preventDefault();
            return;
        }
        hideGlobalLoader();
        sendButton?.setAttribute("disabled", "disabled");
        sendButton?.classList.add("is-sending");
    });
});
