document.addEventListener("DOMContentLoaded", () => {
    const textarea = document.getElementById("aiQuestion");
    const sendButton = document.getElementById("aiSendButton");
    const charCount = document.getElementById("aiCharCount");
    const composer = document.getElementById("aiComposer");
    const sidebar = document.getElementById("chatSidebar");
    const overlay = document.getElementById("chatSidebarOverlay");
    const openButton = document.getElementById("chatSidebarOpen");
    const closeButton = document.getElementById("chatSidebarClose");
    const chatScroll = document.getElementById("chatScroll");

    const updateComposer = () => {
        if (!textarea) return;
        textarea.style.height = "auto";
        textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
        const length = textarea.value.length;
        if (charCount) charCount.textContent = `${length} / 1500`;
        if (sendButton) sendButton.disabled = textarea.value.trim().length === 0;
    };

    textarea?.addEventListener("input", updateComposer);
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
        document.body.classList.add("ai-sidebar-visible");
    };
    const closeSidebar = () => {
        sidebar?.classList.remove("is-open");
        overlay?.classList.remove("is-visible");
        document.body.classList.remove("ai-sidebar-visible");
    };

    openButton?.addEventListener("click", openSidebar);
    closeButton?.addEventListener("click", closeSidebar);
    overlay?.addEventListener("click", closeSidebar);

    document.querySelectorAll("[data-copy-answer]").forEach((button) => {
        button.addEventListener("click", async () => {
            const text = button.closest(".ai-message-body")?.querySelector(".ai-answer-text")?.textContent?.trim();
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

    if (chatScroll) chatScroll.scrollTop = chatScroll.scrollHeight;
});
