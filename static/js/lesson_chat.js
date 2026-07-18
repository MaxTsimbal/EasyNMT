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

    const scrollToBottom = ({ smooth = false } = {}) => {
        messages.scrollTo({
            top: messages.scrollHeight,
            behavior: smooth ? "smooth" : "auto"
        });
    };

    const cleanEasyPrefix = (text) => text
        .replace(/^\s*(?:easy\s*:\s*)+/i, "")
        .replace(/^\s*(?:easy\s*[—–-]\s*)+/i, "")
        .trimStart();

    const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

    const typeInto = async (paragraph, sourceText) => {
        const text = cleanEasyPrefix(sourceText);
        paragraph.textContent = "";
        paragraph.classList.add("lesson-easy-streaming");

        let index = 0;
        while (index < text.length) {
            const left = text.length - index;
            const size = left > 180 ? 5 : left > 70 ? 3 : 2;
            const chunk = text.slice(index, index + size);
            paragraph.textContent += chunk;
            index += chunk.length;
            scrollToBottom();

            const last = chunk.at(-1) || "";
            if (last === "\n") await sleep(65);
            else if (/[.!?]/.test(last)) await sleep(55);
            else if (/[,;:]/.test(last)) await sleep(28);
            else await sleep(12);
        }

        paragraph.classList.remove("lesson-easy-streaming");
        scrollToBottom({ smooth: true });
    };

    let lockedScrollY = 0;

    const syncVisualViewport = () => {
        const viewport = window.visualViewport;
        const height = viewport?.height || window.innerHeight;
        const offsetTop = viewport?.offsetTop || 0;
        document.documentElement.style.setProperty("--easy-visual-height", `${Math.round(height)}px`);
        document.documentElement.style.setProperty("--easy-visual-top", `${Math.round(offsetTop)}px`);
        if (panel.classList.contains("is-open")) scrollToBottom();
    };

    const lockPage = () => {
        lockedScrollY = window.scrollY;
        document.body.style.position = "fixed";
        document.body.style.top = `-${lockedScrollY}px`;
        document.body.style.left = "0";
        document.body.style.right = "0";
        document.body.style.width = "100%";
    };

    const unlockPage = () => {
        document.body.style.position = "";
        document.body.style.top = "";
        document.body.style.left = "";
        document.body.style.right = "";
        document.body.style.width = "";
        window.scrollTo(0, lockedScrollY);
    };

    syncVisualViewport();
    window.visualViewport?.addEventListener("resize", syncVisualViewport);
    window.visualViewport?.addEventListener("scroll", syncVisualViewport);
    window.addEventListener("orientationchange", () => window.setTimeout(syncVisualViewport, 120));

    const setOpen = (open) => {
        panel.classList.toggle("is-open", open);
        backdrop.classList.toggle("is-visible", open);
        document.body.classList.toggle("lesson-easy-open", open);
        panel.setAttribute("aria-hidden", String(!open));
        backdrop.setAttribute("aria-hidden", String(!open));
        launcher.setAttribute("aria-expanded", String(open));

        if (open) {
            lastFocused = document.activeElement;
            syncVisualViewport();
            lockPage();
            window.setTimeout(() => {
                input.focus({ preventScroll: true });
                syncVisualViewport();
                scrollToBottom();
            }, 180);
        } else {
            unlockPage();
            if (lastFocused instanceof HTMLElement) {
                lastFocused.focus({ preventScroll: true });
            }
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
        return { article, paragraph };
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
            loadingMessage.article.remove();
            const assistantMessage = createMessage("assistant", "");
            await typeInto(assistantMessage.paragraph, text);
        } catch (error) {
            loadingMessage.article.remove();
            const assistantMessage = createMessage("assistant", "");
            await typeInto(assistantMessage.paragraph, "Зв’язок перервався. Перевір інтернет і повтори запит.");
        } finally {
            busy = false;
            sendButton?.removeAttribute("disabled");
            input.focus({ preventScroll: true });
        }
    });

    window.addEventListener("pagehide", () => {
        if (panel.classList.contains("is-open")) unlockPage();
    });

    autoGrow();
})();
