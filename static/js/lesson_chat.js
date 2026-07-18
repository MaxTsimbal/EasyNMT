"use strict";

(() => {
    const launcher = document.getElementById("lessonEasyLauncher");
    const panel = document.getElementById("lessonEasyPanel");
    const backdrop = document.getElementById("lessonEasyBackdrop");
    const closeButton = document.getElementById("lessonEasyClose");
    const form = document.getElementById("lessonEasyComposer");
    const input = document.getElementById("lessonEasyInput");
    const sendButton = document.getElementById("lessonEasySend");
    const messages = document.getElementById("lessonEasyMessages");

    if (!launcher || !panel || !backdrop || !form || !input || !messages) return;

    const endpoint = panel.dataset.endpoint;
    const lessonId = panel.dataset.lessonId;
    let busy = false;
    let lastFocused = null;

    const scrollToBottom = () => {
        messages.scrollTop = messages.scrollHeight;
    };

    const setOpen = (open) => {
        panel.classList.toggle("is-open", open);
        backdrop.classList.toggle("is-visible", open);
        document.body.classList.toggle("lesson-easy-open", open);
        panel.setAttribute("aria-hidden", String(!open));
        backdrop.setAttribute("aria-hidden", String(!open));
        launcher.setAttribute("aria-expanded", String(open));

        if (open) {
            lastFocused = document.activeElement;
            window.setTimeout(() => {
                input.focus({ preventScroll: true });
                scrollToBottom();
            }, 180);
        } else if (lastFocused instanceof HTMLElement) {
            lastFocused.focus({ preventScroll: true });
        }
    };

    const autoGrow = () => {
        input.style.height = "auto";
        input.style.height = `${Math.min(input.scrollHeight, 132)}px`;
    };

    const createMessage = (role, text, { loading = false } = {}) => {
        const article = document.createElement("article");
        article.className = `lesson-easy-message lesson-easy-message-${role}`;

        if (role === "assistant") {
            const avatar = document.createElement("span");
            avatar.className = "lesson-easy-mini-avatar";
            const image = document.createElement("img");
            image.src = launcher.querySelector("img")?.src || "";
            image.alt = "";
            avatar.appendChild(image);
            article.appendChild(avatar);
        }

        const content = document.createElement("div");
        if (role === "assistant") {
            const name = document.createElement("b");
            name.textContent = "Easy";
            content.appendChild(name);
        }

        const paragraph = document.createElement("p");
        paragraph.textContent = text;
        if (loading) {
            paragraph.className = "lesson-easy-typing";
            paragraph.innerHTML = "<span></span><span></span><span></span>";
        }
        content.appendChild(paragraph);
        article.appendChild(content);
        messages.appendChild(article);
        scrollToBottom();
        return article;
    };

    launcher.addEventListener("click", () => setOpen(!panel.classList.contains("is-open")));
    closeButton?.addEventListener("click", () => setOpen(false));
    backdrop.addEventListener("click", () => setOpen(false));

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && panel.classList.contains("is-open")) {
            setOpen(false);
        }
    });

    input.addEventListener("input", autoGrow);
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (!busy && input.value.trim()) form.requestSubmit();
        }
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const question = input.value.trim();
        if (!question || busy || !endpoint) return;

        busy = true;
        sendButton?.setAttribute("disabled", "disabled");
        createMessage("user", question);
        input.value = "";
        autoGrow();
        const loadingMessage = createMessage("assistant", "", { loading: true });

        try {
            const response = await fetch(endpoint, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                credentials: "same-origin",
                body: JSON.stringify({ question, lesson_id: lessonId })
            });

            const data = await response.json().catch(() => ({}));
            const text = data.answer || data.error || "Не вдалося отримати відповідь. Спробуй ще раз.";
            loadingMessage.remove();
            createMessage("assistant", text);
        } catch (error) {
            loadingMessage.remove();
            createMessage("assistant", "Зв’язок перервався. Перевір інтернет і повтори запит.");
        } finally {
            busy = false;
            sendButton?.removeAttribute("disabled");
            input.focus({ preventScroll: true });
        }
    });

    autoGrow();
})();
