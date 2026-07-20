"use strict";

(() => {
    const launcher = document.getElementById("contextualEasyLauncher");
    const panel = document.getElementById("contextualEasyPanel");
    const backdrop = document.getElementById("contextualEasyBackdrop");
    const closeButton = document.getElementById("contextualEasyClose");
    const messages = document.getElementById("contextualEasyMessages");
    const contextLabel = document.getElementById("contextualEasyContextLabel");
    const quickActions = document.getElementById("contextualEasyQuickActions");
    const form = document.getElementById("contextualEasyComposer");
    const input = document.getElementById("contextualEasyInput");
    const sendButton = document.getElementById("contextualEasySend");

    if (!launcher || !panel || !messages || !form || !input) return;

    const surface = panel.dataset.surface || "lesson";
    const endpoint = panel.dataset.endpoint || "";
    const csrf = panel.dataset.csrf || "";
    const attemptToken = panel.dataset.attemptToken || "";
    const histories = new Map();
    let activeContextKey = surface === "quiz" ? "" : "lesson:overview";
    let activeQuestionId = "";
    let activeSectionId = "";
    let busy = false;

    const isMobile = () => window.matchMedia("(max-width: 720px)").matches;

    const cleanText = (value) => String(value || "").replace(/^\s*(?:Easy|Ізі)\s*:\s*/i, "").trim();

    const scrollToBottom = () => {
        messages.scrollTop = messages.scrollHeight;
    };

    const createMessage = (role, text, { loading = false } = {}) => {
        const article = document.createElement("article");
        article.className = `contextual-easy-message contextual-easy-message-${role}`;

        if (role === "assistant") {
            const avatar = document.createElement("span");
            avatar.className = "contextual-easy-mini-avatar";
            const image = document.createElement("img");
            image.src = launcher.querySelector("img")?.src || "";
            image.alt = "";
            avatar.appendChild(image);
            article.appendChild(avatar);
        }

        const bubble = document.createElement("div");
        if (role === "assistant") {
            const name = document.createElement("b");
            name.textContent = "Easy";
            bubble.appendChild(name);
        }
        const paragraph = document.createElement("p");
        if (loading) {
            paragraph.className = "contextual-easy-typing";
            paragraph.innerHTML = "<span></span><span></span><span></span>";
        } else {
            paragraph.textContent = cleanText(text);
        }
        bubble.appendChild(paragraph);
        article.appendChild(bubble);
        messages.appendChild(article);
        scrollToBottom();
        return { article, paragraph };
    };

    const contextIntro = () => {
        if (surface === "quiz") {
            return activeQuestionId
                ? "Поясню умову простіше або нагадаю правило. Готову відповідь, правильний варіант чи перевірку твоєї відповіді під час тесту не дам."
                : "Натисни «Пояснити з Easy» біля питання. Я побачу саме його й допоможу розібрати формулювання без готової відповіді.";
        }
        return "Я бачу цей урок і можу пояснити поточний фрагмент простіше, розібрати правило або дати інший приклад.";
    };

    const currentHistory = () => histories.get(activeContextKey) || [];

    const renderContextHistory = () => {
        messages.innerHTML = "";
        const history = currentHistory();
        if (!history.length) {
            createMessage("assistant", contextIntro());
            return;
        }
        history.forEach((item) => createMessage(item.role, item.text));
    };

    const setOpen = (open) => {
        panel.classList.toggle("is-open", open);
        launcher.classList.toggle("is-hidden", open);
        panel.setAttribute("aria-hidden", String(!open));
        launcher.setAttribute("aria-expanded", String(open));
        if (backdrop) {
            backdrop.classList.toggle("is-visible", open && isMobile());
            backdrop.setAttribute("aria-hidden", String(!(open && isMobile())));
        }
        document.body.classList.toggle("contextual-easy-mobile-open", open && isMobile());
        if (open) {
            renderContextHistory();
            window.setTimeout(() => input.focus({ preventScroll: true }), 120);
        }
    };

    const updateContext = ({ key, label, questionId = "", sectionId = "" }) => {
        if (!key) return;
        activeContextKey = key;
        activeQuestionId = questionId;
        activeSectionId = sectionId;
        if (contextLabel) contextLabel.textContent = label;
        renderContextHistory();
    };

    const appendHistory = (role, text) => {
        const history = currentHistory().slice(-10);
        history.push({ role, text: cleanText(text).slice(0, 1800) });
        histories.set(activeContextKey, history.slice(-12));
    };

    const submitMessage = async (message) => {
        const text = String(message || "").trim();
        if (!text || busy || !endpoint) return;
        if (surface === "quiz" && !activeQuestionId) {
            createMessage("assistant", "Спочатку обери питання кнопкою «Пояснити з Easy».");
            return;
        }

        busy = true;
        sendButton?.setAttribute("disabled", "disabled");
        appendHistory("user", text);
        createMessage("user", text);
        input.value = "";
        input.style.height = "auto";
        const loading = createMessage("assistant", "", { loading: true });

        const payload = {
            message: text,
            history: currentHistory().slice(0, -1),
        };
        if (surface === "quiz") {
            payload.attempt_token = attemptToken;
            payload.question_id = activeQuestionId;
        } else {
            payload.section_id = activeSectionId;
        }

        try {
            const response = await fetch(endpoint, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-CSRF-Token": csrf,
                },
                body: JSON.stringify(payload),
            });
            const data = await response.json().catch(() => ({}));
            const answer = cleanText(data.answer || data.message || data.error || "Не вдалося отримати пояснення. Спробуй ще раз.");
            loading.article.remove();
            appendHistory("assistant", answer);
            createMessage("assistant", answer);
        } catch (_error) {
            loading.article.remove();
            const answer = "Зв’язок перервався. Перевір інтернет і повтори запит.";
            appendHistory("assistant", answer);
            createMessage("assistant", answer);
        } finally {
            busy = false;
            sendButton?.removeAttribute("disabled");
            input.focus({ preventScroll: true });
        }
    };

    launcher.addEventListener("click", () => setOpen(!panel.classList.contains("is-open")));
    closeButton?.addEventListener("click", () => setOpen(false));
    backdrop?.addEventListener("click", () => setOpen(false));
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && panel.classList.contains("is-open")) setOpen(false);
    });

    input.addEventListener("input", () => {
        input.style.height = "auto";
        input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
    });
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            form.requestSubmit();
        }
    });
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        submitMessage(input.value);
    });
    quickActions?.addEventListener("click", (event) => {
        const button = event.target.closest("[data-easy-message]");
        if (!button) return;
        setOpen(true);
        submitMessage(button.dataset.easyMessage || "");
    });

    if (surface === "quiz") {
        const questionCards = [...document.querySelectorAll("[data-easy-question-id]")];
        const selectQuestion = (card, { open = false } = {}) => {
            if (!card) return;
            questionCards.forEach((item) => item.classList.toggle("is-easy-active", item === card));
            const id = card.dataset.easyQuestionId || "";
            const number = card.dataset.easyQuestionNumber || "";
            const prompt = card.dataset.easyQuestionPrompt || "Поточне питання";
            updateContext({
                key: `quiz:${id}`,
                label: `Питання ${number}: ${prompt}`,
                questionId: id,
            });
            if (open) setOpen(true);
        };

        questionCards.forEach((card) => {
            card.querySelector("[data-easy-open-question]")?.addEventListener("click", () => selectQuestion(card, { open: true }));
        });

        if (questionCards.length) {
            selectQuestion(questionCards[0]);
            const observer = new IntersectionObserver((entries) => {
                const visible = entries
                    .filter((entry) => entry.isIntersecting)
                    .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
                if (visible && !panel.matches(":focus-within")) selectQuestion(visible.target);
            }, { rootMargin: "-28% 0px -48% 0px", threshold: [0.2, 0.45, 0.7] });
            questionCards.forEach((card) => observer.observe(card));
        }
    } else {
        const sections = [...document.querySelectorAll("[data-easy-section]")];
        const setSection = (section) => {
            if (!section) return;
            const id = section.dataset.easySection || "";
            const title = section.querySelector("h2")?.textContent?.trim() || "Поточний фрагмент уроку";
            activeSectionId = id;
            activeContextKey = `lesson:${id || "overview"}`;
            if (contextLabel) contextLabel.textContent = title;
            if (panel.classList.contains("is-open")) renderContextHistory();
        };
        if (sections.length) {
            setSection(sections[0]);
            const observer = new IntersectionObserver((entries) => {
                const visible = entries
                    .filter((entry) => entry.isIntersecting)
                    .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
                if (visible) setSection(visible.target);
            }, { rootMargin: "-20% 0px -58% 0px", threshold: [0.15, 0.4, 0.7] });
            sections.forEach((section) => observer.observe(section));
        }
    }

    window.addEventListener("resize", () => {
        if (!isMobile()) {
            backdrop?.classList.remove("is-visible");
            document.body.classList.remove("contextual-easy-mobile-open");
        } else if (panel.classList.contains("is-open")) {
            backdrop?.classList.add("is-visible");
            document.body.classList.add("contextual-easy-mobile-open");
        }
    });
})();
