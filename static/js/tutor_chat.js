"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const body = document.body;
    const app = document.querySelector(".easy-chat-app");
    const textarea = document.getElementById("aiQuestion");
    const sendButton = document.getElementById("aiSendButton");
    const charCount = document.getElementById("aiCharCount");
    const composer = document.getElementById("aiComposer");
    const sidebar = document.getElementById("chatSidebar");
    const overlay = document.getElementById("chatSidebarOverlay");
    const openButton = document.getElementById("chatSidebarOpen");
    const closeButton = document.getElementById("chatSidebarClose");
    const chatScroll = document.getElementById("chatScroll");

    /* The full-screen page loader never belongs inside Easy Chat. */
    const disablePageLoader = () => {
        const loader = document.getElementById("pageLoader");
        loader?.classList.add("hidden");
        loader?.setAttribute("aria-hidden", "true");
        body.classList.remove("easy-transition-loading");
    };
    disablePageLoader();
    window.addEventListener("pageshow", disablePageLoader);

    /* Keep the app inside the real iOS/Telegram visual viewport. */
    const syncVisualViewport = () => {
        const viewport = window.visualViewport;
        const height = Math.round(viewport?.height || window.innerHeight);
        const top = Math.round(viewport?.offsetTop || 0);
        document.documentElement.style.setProperty("--easy-chat-height", `${height}px`);
        document.documentElement.style.setProperty("--easy-chat-top", `${top}px`);
        if (app) app.style.height = `${height}px`;
        requestAnimationFrame(() => {
            if (chatScroll) chatScroll.scrollTop = chatScroll.scrollHeight;
        });
    };

    syncVisualViewport();
    window.visualViewport?.addEventListener("resize", syncVisualViewport);
    window.visualViewport?.addEventListener("scroll", syncVisualViewport);
    window.addEventListener("orientationchange", () => window.setTimeout(syncVisualViewport, 120));

    const updateComposer = () => {
        if (!textarea) return;
        textarea.style.height = "auto";
        textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
        const length = textarea.value.length;
        if (charCount) charCount.textContent = `${length} / 1500`;
        if (sendButton) sendButton.disabled = textarea.value.trim().length === 0;
        syncVisualViewport();
    };

    textarea?.addEventListener("input", updateComposer);
    textarea?.addEventListener("focus", () => {
        window.setTimeout(() => {
            syncVisualViewport();
            chatScroll?.scrollTo({ top: chatScroll.scrollHeight, behavior: "smooth" });
        }, 80);
    });
    textarea?.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (textarea.value.trim()) composer?.requestSubmit();
        }
    });
    updateComposer();

    const openSidebar = () => {
        sidebar?.classList.add("is-open");
        overlay?.classList.add("is-visible");
        body.classList.add("ai-sidebar-visible");
    };
    const closeSidebar = () => {
        sidebar?.classList.remove("is-open");
        overlay?.classList.remove("is-visible");
        body.classList.remove("ai-sidebar-visible");
    };

    openButton?.addEventListener("click", openSidebar);
    closeButton?.addEventListener("click", closeSidebar);
    overlay?.addEventListener("click", closeSidebar);

    const cleanEasyPrefix = (text) => text
        .replace(/^\s*(?:easy\s*:\s*)+/i, "")
        .replace(/^\s*(?:easy\s*[—–-]\s*)+/i, "")
        .trimStart();

    const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

    const typeAnswer = async (element) => {
        const raw = cleanEasyPrefix(element.textContent || "");
        if (!raw || element.dataset.typed === "true") return;
        element.dataset.typed = "true";
        element.textContent = "";
        element.classList.add("is-typing");

        let index = 0;
        while (index < raw.length) {
            const remaining = raw.length - index;
            const chunkSize = remaining > 180 ? 5 : remaining > 70 ? 3 : 2;
            const chunk = raw.slice(index, index + chunkSize);
            element.textContent += chunk;
            index += chunk.length;

            if (chatScroll) chatScroll.scrollTop = chatScroll.scrollHeight;

            const last = chunk.at(-1) || "";
            if (last === "\n") await sleep(65);
            else if (/[.!?]/.test(last)) await sleep(55);
            else if (/[,;:]/.test(last)) await sleep(28);
            else await sleep(12);
        }

        element.classList.remove("is-typing");
        if (chatScroll) chatScroll.scrollTop = chatScroll.scrollHeight;
    };

    document.querySelectorAll(".ai-answer-text").forEach((element) => {
        typeAnswer(element);
    });

    document.querySelectorAll("[data-copy-answer]").forEach((button) => {
        button.addEventListener("click", async () => {
            const text = button.closest(".easy-assistant-content")?.querySelector(".ai-answer-text")?.textContent?.trim();
            if (!text) return;
            try {
                await navigator.clipboard.writeText(text);
                button.textContent = "✓";
                window.setTimeout(() => { button.textContent = "⧉"; }, 1400);
            } catch (_) {
                button.title = "Не вдалося скопіювати";
            }
        });
    });

    composer?.addEventListener("submit", () => {
        disablePageLoader();
        sendButton?.setAttribute("disabled", "disabled");
    });

    if (chatScroll) chatScroll.scrollTop = chatScroll.scrollHeight;
});
