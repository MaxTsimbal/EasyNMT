"use strict";

(() => {
    const launcher = document.getElementById("contextualEasyLauncher");
    const panel = document.getElementById("contextualEasyPanel");
    const backdrop = document.getElementById("contextualEasyBackdrop");
    const closeButton = document.getElementById("contextualEasyClose");
    const messages = document.getElementById("contextualEasyMessages");
    const contextLabel = document.getElementById("contextualEasyContextLabel");
    const modeLabel = document.getElementById("contextualEasyMode");
    const quickActions = document.getElementById("contextualEasyQuickActions");
    const form = document.getElementById("contextualEasyComposer");
    const input = document.getElementById("contextualEasyInput");
    const sendButton = document.getElementById("contextualEasySend");

    if (!launcher || !panel || !messages || !form || !input || !sendButton) return;

    const markdown = window.EasyChatV2Markdown;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const surface = panel.dataset.surface || "lesson";
    const endpoint = panel.dataset.endpoint || "";
    const statusEndpoint = panel.dataset.statusEndpoint || "";
    const csrf = panel.dataset.csrf || "";
    const attemptToken = panel.dataset.attemptToken || "";
    const histories = new Map();

    let activeContextKey = surface === "quiz" ? "" : "lesson:overview";
    let activeQuestionId = "";
    let activeSectionId = "";
    let busy = false;
    let controller = null;
    let autoFollow = true;

    const isMobile = () => window.matchMedia("(max-width: 720px)").matches;
    const cleanText = (value) => String(value || "").replace(/^\s*(?:Easy|Ізі)\s*:\s*/i, "").trim();

    const hideGlobalLoader = () => {
        const loader = document.getElementById("pageLoader");
        loader?.classList.add("hidden");
        loader?.setAttribute("aria-hidden", "true");
        document.body.classList.remove("easy-transition-loading");
    };

    const isNearBottom = () => (
        messages.scrollHeight - messages.scrollTop - messages.clientHeight < 90
    );

    const scrollToBottom = (behavior = "auto", force = false) => {
        if (!force && !autoFollow && !isNearBottom()) return;
        messages.scrollTo({
            top: messages.scrollHeight,
            behavior: reduceMotion ? "auto" : behavior,
        });
    };

    messages.addEventListener("scroll", () => {
        autoFollow = isNearBottom();
    }, { passive: true });

    const setMode = (mode) => {
        if (!modeLabel) return;
        const normalized = String(mode || "").toLowerCase();
        const modes = {
            openai: ["Онлайн AI", "is-online"],
            offline: ["Офлайн підказка", "is-offline"],
            limit: ["Ліміт AI", "is-limit"],
            guarded: ["Без готових відповідей", "is-guarded"],
            error: ["Помилка AI", "is-error"],
            checking: ["Перевіряю AI", "is-checking"],
        };
        const [label, className] = modes[normalized] || ["Easy готовий", "is-ready"];
        modeLabel.className = `contextual-easy-mode ${className}`;
        modeLabel.textContent = label;
    };

    const checkAiStatus = async () => {
        if (!statusEndpoint) {
            setMode("ready");
            return;
        }
        try {
            const response = await fetch(statusEndpoint, {
                credentials: "same-origin",
                headers: { "Accept": "application/json", "X-Requested-With": "XMLHttpRequest" },
            });
            const data = await response.json().catch(() => ({}));
            setMode(data.mode === "openai" ? "openai" : "offline");
        } catch {
            setMode("offline");
        }
    };

    const renderRichText = async (node, text) => {
        const value = cleanText(text);
        if (markdown?.render) {
            node.innerHTML = markdown.render(value);
            await markdown.typesetMath?.(node);
        } else {
            node.textContent = value;
        }
    };

    const createMessage = (role, text, { loading = false, pending = false } = {}) => {
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

        const content = document.createElement("div");
        content.className = "contextual-easy-answer";
        if (loading) {
            content.classList.add("contextual-easy-typing");
            content.innerHTML = "<span></span><span></span><span></span><small>Easy думає</small>";
        } else if (pending) {
            content.classList.add("is-streaming");
        } else if (role === "assistant") {
            renderRichText(content, text);
        } else {
            content.textContent = cleanText(text);
        }

        bubble.appendChild(content);
        article.appendChild(bubble);
        messages.appendChild(article);
        autoFollow = true;
        scrollToBottom("smooth", true);
        return { article, content };
    };

    const typeAnswer = async (node, text, signal) => {
        const value = cleanText(text);
        node.classList.remove("contextual-easy-typing");
        node.classList.add("is-streaming");
        node.textContent = "";

        if (reduceMotion || value.length > 2400) {
            node.textContent = value;
        } else {
            const tokens = value.match(/\S+\s*/g) || [value];
            for (const token of tokens) {
                if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
                node.textContent += token;
                scrollToBottom("auto");
                const delay = /[.!?]\s*$/.test(token) ? 52 : /[,;:]\s*$/.test(token) ? 28 : 13;
                await new Promise((resolve) => window.setTimeout(resolve, delay));
            }
        }

        node.classList.remove("is-streaming");
        await renderRichText(node, value);
        scrollToBottom("smooth");
    };

    const contextIntro = () => {
        if (surface === "quiz") {
            return activeQuestionId
                ? "Я бачу саме це питання. Поясню умову простіше, нагадаю правило або покажу інший схожий приклад без готової відповіді."
                : "Натисни «Пояснити з Easy» біля питання. Я побачу саме його й допоможу розібрати формулювання без готової відповіді.";
        }
        return "Я бачу цей урок і поточний фрагмент. Можу пояснити його простіше, розібрати правило або дати інший приклад.";
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
        autoFollow = true;
        scrollToBottom("auto", true);
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
            hideGlobalLoader();
            renderContextHistory();
            window.setTimeout(() => input.focus({ preventScroll: true }), 120);
        }
    };

    const stopCurrentRequest = () => {
        if (!busy) return;
        controller?.abort();
    };

    const setBusy = (value) => {
        busy = Boolean(value);
        panel.classList.toggle("is-generating", busy);
        messages.setAttribute("aria-busy", busy ? "true" : "false");
        sendButton.classList.toggle("is-stop", busy);
        sendButton.setAttribute("aria-label", busy ? "Зупинити відповідь" : "Надіслати запитання");
    };

    const updateContext = ({ key, label, questionId = "", sectionId = "" }) => {
        if (!key) return;
        if (busy) stopCurrentRequest();
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

    const requestAnswer = async (payload, signal) => {
        const response = await fetch(endpoint, {
            method: "POST",
            credentials: "same-origin",
            signal,
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRF-Token": csrf,
            },
            body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) {
            throw new Error(data.message || data.error || `Помилка ${response.status}`);
        }
        return data;
    };

    const submitMessage = async (message) => {
        const text = String(message || "").trim();
        if (busy) {
            stopCurrentRequest();
            return;
        }
        if (!text || !endpoint) return;
        if (surface === "quiz" && !activeQuestionId) {
            createMessage("assistant", "Спочатку обери питання кнопкою «Пояснити з Easy».");
            return;
        }

        hideGlobalLoader();
        setBusy(true);
        controller = new AbortController();
        appendHistory("user", text);
        createMessage("user", text);
        input.value = "";
        input.style.height = "auto";
        const pending = createMessage("assistant", "", { loading: true });

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
            const data = await requestAnswer(payload, controller.signal);
            const answer = cleanText(data.answer || data.message || "Не вдалося отримати пояснення. Спробуй ще раз.");
            setMode(data.mode || "ready");
            await typeAnswer(pending.content, answer, controller.signal);
            appendHistory("assistant", answer);
        } catch (error) {
            pending.article.remove();
            if (error.name === "AbortError") {
                createMessage("assistant", "Відповідь зупинено. Можеш сформулювати запит інакше.");
            } else {
                setMode("error");
                const answer = `Не вдалося отримати пояснення. ${error.message || "Перевір з’єднання та повтори запит."}`;
                appendHistory("assistant", answer);
                createMessage("assistant", answer);
            }
        } finally {
            controller = null;
            setBusy(false);
            hideGlobalLoader();
            const restoreFocus = !isMobile() || document.activeElement === input;
            if (restoreFocus) input.focus({ preventScroll: true });
        }
    };

    launcher.addEventListener("click", () => setOpen(!panel.classList.contains("is-open")));
    closeButton?.addEventListener("click", () => setOpen(false));
    backdrop?.addEventListener("click", () => setOpen(false));
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && busy) {
            stopCurrentRequest();
        } else if (event.key === "Escape" && panel.classList.contains("is-open")) {
            setOpen(false);
        }
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
        event.stopPropagation();
        hideGlobalLoader();
        if (busy) stopCurrentRequest();
        else submitMessage(input.value);
    });
    sendButton.addEventListener("click", (event) => {
        if (!busy) return;
        event.preventDefault();
        stopCurrentRequest();
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
                if (visible && !panel.matches(":focus-within") && !busy) selectQuestion(visible.target);
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
            if (panel.classList.contains("is-open") && !busy) renderContextHistory();
        };
        if (sections.length) {
            setSection(sections[0]);
            const observer = new IntersectionObserver((entries) => {
                const visible = entries
                    .filter((entry) => entry.isIntersecting)
                    .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
                if (visible && !busy) setSection(visible.target);
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

    hideGlobalLoader();
    checkAiStatus();
})();
