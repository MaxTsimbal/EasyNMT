"use strict";

(() => {
    const MAX_STORED_MESSAGES = 30;
    const TYPE_DELAY = 9;

    const escapeHtml = (value) => String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");

    const inlineMarkup = (value) => escapeHtml(value)
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

    const cleanAnswerPrefix = (value) => String(value || "")
        .replace(/^\s*(?:Easy\s*[:—–-]\s*)+/i, "")
        .trimStart();

    const formatText = (text) => {
        const source = String(text || "").replace(/\r\n?/g, "\n").trim();
        if (!source) return "";

        const segments = source.split(/```/);
        const html = [];

        segments.forEach((segment, index) => {
            if (index % 2 === 1) {
                const lines = segment.replace(/^\n|\n$/g, "").split("\n");
                if (lines[0] && /^[a-z0-9_+-]+$/i.test(lines[0].trim())) lines.shift();
                html.push(`<pre><code>${escapeHtml(lines.join("\n"))}</code></pre>`);
                return;
            }

            const lines = segment.split("\n");
            let listType = "";
            let paragraph = [];

            const flushParagraph = () => {
                if (!paragraph.length) return;
                html.push(`<p>${paragraph.map(inlineMarkup).join("<br>")}</p>`);
                paragraph = [];
            };

            const closeList = () => {
                if (!listType) return;
                html.push(`</${listType}>`);
                listType = "";
            };

            lines.forEach((rawLine) => {
                const line = rawLine.trimEnd();
                const trimmed = line.trim();

                if (!trimmed) {
                    flushParagraph();
                    closeList();
                    return;
                }

                const heading = trimmed.match(/^(#{2,4})\s+(.+)$/);
                if (heading) {
                    flushParagraph();
                    closeList();
                    const level = heading[1].length;
                    html.push(`<h${level}>${inlineMarkup(heading[2])}</h${level}>`);
                    return;
                }

                const unordered = trimmed.match(/^[-•]\s+(.+)$/);
                const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
                if (unordered || ordered) {
                    flushParagraph();
                    const nextType = unordered ? "ul" : "ol";
                    if (listType && listType !== nextType) closeList();
                    if (!listType) {
                        listType = nextType;
                        html.push(`<${listType}>`);
                    }
                    html.push(`<li>${inlineMarkup((unordered || ordered)[1])}</li>`);
                    return;
                }

                const quote = trimmed.match(/^>\s?(.+)$/);
                if (quote) {
                    flushParagraph();
                    closeList();
                    html.push(`<blockquote>${inlineMarkup(quote[1])}</blockquote>`);
                    return;
                }

                closeList();
                paragraph.push(trimmed);
            });

            flushParagraph();
            closeList();
        });

        return html.join("");
    };

    document.addEventListener("DOMContentLoaded", () => {
        const body = document.body;
        const root = document.documentElement;
        const app = document.getElementById("easyChatApp");
        if (!app) return;

        const sidebar = document.getElementById("easyChatSidebar");
        const sidebarOpen = document.getElementById("easyChatSidebarOpen");
        const sidebarClose = document.getElementById("easyChatSidebarClose");
        const overlay = document.getElementById("easyChatOverlay");
        const newChatButton = document.getElementById("easyChatNew");
        const thread = document.getElementById("easyChatThread");
        const messages = document.getElementById("easyChatMessages");
        const welcome = document.getElementById("easyChatWelcome");
        const welcomeTemplate = welcome?.cloneNode(true) || null;
        const composer = document.getElementById("easyChatComposer");
        const input = document.getElementById("easyChatInput");
        const sendButton = document.getElementById("easyChatSend");
        const count = document.getElementById("easyChatCount");
        const jump = document.getElementById("easyChatJump");
        const toast = document.getElementById("easyChatToast");
        const conversationStatus = document.getElementById("easyChatConversationStatus");
        const modeLabel = document.getElementById("easyChatModeLabel");
        const topMode = document.getElementById("easyChatTopMode");
        const statusDot = document.getElementById("easyChatStatusDot");
        const usageText = document.getElementById("easyChatUsageText");
        const usageBar = document.getElementById("easyChatUsageBar");

        const apiUrl = app.dataset.apiUrl || "/api/tutor-chat";
        const storageKey = app.dataset.storageKey || "easy-chat-v12-general";
        const lessonContext = app.dataset.lessonContext === "true";
        const lessonId = app.dataset.lessonId || "";
        const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

        let requestInFlight = false;
        let abortController = null;
        let typingToken = 0;
        let toastTimer = 0;

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
            root.style.setProperty("--easy-chat-height", `${height}px`);
            root.style.setProperty("--easy-chat-top", `${top}px`);
        };

        const nearBottom = () => {
            if (!thread) return true;
            return thread.scrollHeight - thread.scrollTop - thread.clientHeight < 110;
        };

        const scrollToBottom = (behavior = "auto") => {
            if (!thread) return;
            thread.scrollTo({ top: thread.scrollHeight, behavior });
        };

        const showToast = (message) => {
            if (!toast) return;
            window.clearTimeout(toastTimer);
            toast.textContent = message;
            toast.classList.add("is-visible");
            toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2200);
        };

        const openSidebar = () => {
            sidebar?.classList.add("is-open");
            overlay?.classList.add("is-visible");
            body.classList.add("easy-chat-sidebar-open");
        };

        const closeSidebar = () => {
            sidebar?.classList.remove("is-open");
            overlay?.classList.remove("is-visible");
            body.classList.remove("easy-chat-sidebar-open");
        };

        const updateInput = () => {
            if (!input || !sendButton) return;
            input.style.height = "auto";
            input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
            const length = input.value.length;
            if (count) {
                count.textContent = `${length} / 1500`;
                count.classList.toggle("is-visible", length > 1000);
                count.classList.toggle("is-near-limit", length > 1400);
            }
            sendButton.disabled = !requestInFlight && input.value.trim().length === 0;
        };

        const setSending = (value) => {
            requestInFlight = value;
            composer?.classList.toggle("is-sending", value);
            thread?.setAttribute("aria-busy", value ? "true" : "false");
            if (sendButton) {
                sendButton.disabled = !value && !input?.value.trim();
                sendButton.setAttribute("aria-label", value ? "Зупинити відповідь" : "Надіслати");
            }
        };

        const loadStored = () => {
            try {
                const parsed = JSON.parse(window.localStorage.getItem(storageKey) || "[]");
                if (!Array.isArray(parsed)) return [];
                return parsed.filter((item) => item && ["user", "assistant"].includes(item.role) && typeof item.text === "string").slice(-MAX_STORED_MESSAGES);
            } catch {
                return [];
            }
        };

        const saveStored = (items) => {
            try {
                window.localStorage.setItem(storageKey, JSON.stringify(items.slice(-MAX_STORED_MESSAGES)));
            } catch {
                /* The chat still works when storage is blocked. */
            }
        };

        const readDomConversation = () => Array.from(messages?.querySelectorAll("[data-role]") || []).map((node) => {
            const role = node.dataset.role;
            const textNode = role === "user"
                ? node.querySelector(".easy-chat-message__user-bubble")
                : node.querySelector("[data-answer-text]");
            return { role, text: textNode?.dataset.rawText || textNode?.textContent?.trim() || "" };
        }).filter((item) => item.text);

        const storeDomConversation = () => {
            const items = readDomConversation();
            saveStored(items);
            if (conversationStatus) conversationStatus.textContent = items.length ? `${Math.ceil(items.length / 2)} повідомлень` : "Нова розмова";
        };

        const removeWelcome = () => {
            document.getElementById("easyChatWelcome")?.remove();
        };

        const createUserMessage = (text) => {
            const article = document.createElement("article");
            article.className = "easy-chat-message easy-chat-message--user";
            article.dataset.role = "user";
            const bubble = document.createElement("div");
            bubble.className = "easy-chat-message__user-bubble";
            bubble.textContent = text;
            article.appendChild(bubble);
            return article;
        };

        const createAssistantMessage = (text = "", { thinking = false } = {}) => {
            const cleanText = cleanAnswerPrefix(text);
            const article = document.createElement("article");
            article.className = "easy-chat-message easy-chat-message--assistant";
            article.dataset.role = thinking ? "thinking" : "assistant";

            const avatar = document.createElement("div");
            avatar.className = "easy-chat-message__avatar";
            avatar.setAttribute("aria-hidden", "true");
            avatar.innerHTML = '<img src="/static/images/easynmt-mascot.png" alt="">';

            const content = document.createElement("div");
            content.className = "easy-chat-message__content";
            content.innerHTML = '<div class="easy-chat-message__name"><strong>Easy</strong><span>AI-викладач</span></div>';

            if (thinking) {
                const thinkingNode = document.createElement("div");
                thinkingNode.className = "easy-chat-thinking";
                thinkingNode.innerHTML = '<span class="easy-chat-thinking__spark">✦</span><span>Easy думає</span><span class="easy-chat-thinking__dots"><i></i><i></i><i></i></span>';
                content.appendChild(thinkingNode);
            } else {
                const answer = document.createElement("div");
                answer.className = "easy-chat-answer";
                answer.dataset.answerText = "";
                answer.dataset.rawText = cleanText;
                answer.innerHTML = formatText(cleanText);
                content.appendChild(answer);

                const actions = document.createElement("div");
                actions.className = "easy-chat-message__actions";
                actions.innerHTML = `
                    <button type="button" data-copy-message>
                        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>
                        <span>Копіювати</span>
                    </button>
                    <button type="button" data-prompt="Поясни попередню відповідь ще простіше"><span>Простіше</span></button>
                    <button type="button" data-prompt="Покажи попередню відповідь на конкретному прикладі"><span>Приклад</span></button>`;
                content.appendChild(actions);
            }

            article.append(avatar, content);
            return article;
        };

        const renderStoredConversation = () => {
            const stored = loadStored();
            if (!stored.length || !messages) return false;

            messages.innerHTML = "";
            stored.forEach((item) => {
                messages.appendChild(item.role === "user" ? createUserMessage(item.text) : createAssistantMessage(item.text));
            });
            storeDomConversation();
            requestAnimationFrame(() => scrollToBottom());
            return true;
        };

        const typeText = async (element, text) => {
            const token = ++typingToken;
            element.dataset.rawText = text;

            if (prefersReducedMotion || text.length > 4200) {
                element.innerHTML = formatText(text);
                return;
            }

            element.textContent = "";
            element.classList.add("is-typing");
            let index = 0;

            while (index < text.length && token === typingToken) {
                const remaining = text.length - index;
                const chunkSize = remaining > 800 ? 7 : remaining > 300 ? 5 : remaining > 100 ? 3 : 2;
                const chunk = text.slice(index, index + chunkSize);
                element.textContent += chunk;
                index += chunk.length;
                scrollToBottom();

                const last = chunk.at(-1) || "";
                const extra = /[.!?]/.test(last) ? 30 : /[,;:]/.test(last) ? 12 : 0;
                await new Promise((resolve) => window.setTimeout(resolve, TYPE_DELAY + extra));
            }

            if (token === typingToken) {
                element.classList.remove("is-typing");
                element.innerHTML = formatText(text);
                scrollToBottom();
            }
        };

        const updateMode = ({ mode, used, limit }) => {
            const normalized = mode || "demo";
            const label = normalized === "openai" ? "Easy онлайн" : normalized === "limit" ? "Ліміт вичерпано" : "Демо-режим";
            const topLabel = normalized === "openai" ? "онлайн" : normalized === "limit" ? "ліміт вичерпано" : "демо-режим";

            if (modeLabel) modeLabel.textContent = label;
            if (topMode) topMode.textContent = topLabel;
            statusDot?.classList.remove("openai", "limit", "demo");
            statusDot?.classList.add(normalized);
            document.querySelector(".easy-chat-title__copy small i")?.classList.remove("openai", "limit", "demo");
            document.querySelector(".easy-chat-title__copy small i")?.classList.add(normalized);

            if (Number.isFinite(Number(used)) && Number.isFinite(Number(limit))) {
                const safeLimit = Math.max(1, Number(limit));
                const safeUsed = Math.max(0, Number(used));
                if (usageText) usageText.textContent = `${safeUsed}/${safeLimit}`;
                if (usageBar) usageBar.style.width = `${Math.min(100, Math.round(safeUsed / safeLimit * 100))}%`;
            }
        };

        const sendQuestion = async (question) => {
            const cleanQuestion = String(question || "").trim();
            if (!cleanQuestion || requestInFlight || !messages) return;

            hideGlobalLoader();
            removeWelcome();
            messages.appendChild(createUserMessage(cleanQuestion));
            const thinkingMessage = createAssistantMessage("", { thinking: true });
            messages.appendChild(thinkingMessage);
            storeDomConversation();
            scrollToBottom("smooth");

            if (input) {
                input.value = "";
                updateInput();
            }

            const conversationHistory = readDomConversation().slice(0, -1).slice(-8);
            abortController = new AbortController();
            setSending(true);

            try {
                const response = await fetch(apiUrl, {
                    method: "POST",
                    credentials: "same-origin",
                    signal: abortController.signal,
                    headers: {
                        "Content-Type": "application/json",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    body: JSON.stringify({
                        question: cleanQuestion,
                        context: lessonContext ? "lesson" : "general",
                        lesson_id: lessonId,
                        history: conversationHistory,
                    }),
                });

                let data;
                try {
                    data = await response.json();
                } catch {
                    throw new Error("Сервер повернув неочікувану відповідь.");
                }

                if (!response.ok || !data.ok) {
                    throw new Error(data.error || `Помилка ${response.status}`);
                }

                thinkingMessage.remove();
                const answerText = cleanAnswerPrefix(data.answer || "Не вдалося сформувати відповідь.");
                const assistantMessage = createAssistantMessage(answerText);
                messages.appendChild(assistantMessage);
                const answerNode = assistantMessage.querySelector("[data-answer-text]");
                if (answerNode) await typeText(answerNode, answerText);
                updateMode(data);
                storeDomConversation();
            } catch (error) {
                thinkingMessage.remove();
                if (error.name === "AbortError") {
                    showToast("Відповідь зупинено");
                } else {
                    const message = createAssistantMessage(`Не вдалося отримати відповідь. ${error.message || "Перевір інтернет і спробуй ще раз."}`);
                    message.classList.add("is-error");
                    messages.appendChild(message);
                    storeDomConversation();
                    console.error("Easy Chat request failed:", error);
                }
            } finally {
                abortController = null;
                setSending(false);
                updateInput();
                input?.focus({ preventScroll: true });
                scrollToBottom();
            }
        };

        const clearConversation = () => {
            typingToken += 1;
            abortController?.abort();
            try { window.localStorage.removeItem(storageKey); } catch { /* no-op */ }
            if (messages) {
                messages.innerHTML = "";
                if (welcomeTemplate) messages.appendChild(welcomeTemplate.cloneNode(true));
            }
            if (conversationStatus) conversationStatus.textContent = "Нова розмова";
            if (input) input.value = "";
            setSending(false);
            updateInput();
            closeSidebar();
            thread?.scrollTo({ top: 0, behavior: prefersReducedMotion ? "auto" : "smooth" });
            window.setTimeout(() => input?.focus({ preventScroll: true }), 80);
        };

        hideGlobalLoader();
        syncViewport();

        const hasServerConversation = Boolean(messages?.querySelector("[data-role='user'], [data-role='assistant']"));
        if (hasServerConversation) {
            removeWelcome();
            messages?.querySelectorAll("[data-answer-text]").forEach((node) => {
                const raw = cleanAnswerPrefix(node.textContent?.trim() || "");
                node.dataset.rawText = raw;
                node.innerHTML = formatText(raw);
            });
            storeDomConversation();
        } else {
            renderStoredConversation();
        }

        updateInput();
        requestAnimationFrame(() => scrollToBottom());

        window.addEventListener("pageshow", hideGlobalLoader);
        window.addEventListener("resize", syncViewport, { passive: true });
        window.visualViewport?.addEventListener("resize", () => {
            syncViewport();
            requestAnimationFrame(() => scrollToBottom());
        });
        window.visualViewport?.addEventListener("scroll", syncViewport, { passive: true });

        sidebarOpen?.addEventListener("click", openSidebar);
        sidebarClose?.addEventListener("click", closeSidebar);
        overlay?.addEventListener("click", closeSidebar);
        newChatButton?.addEventListener("click", clearConversation);

        input?.addEventListener("input", updateInput);
        input?.addEventListener("focus", () => window.setTimeout(() => scrollToBottom("smooth"), 100));
        input?.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
                event.preventDefault();
                if (requestInFlight) return;
                sendQuestion(input.value);
            }
        });

        composer?.addEventListener("submit", (event) => {
            event.preventDefault();
            if (requestInFlight) {
                abortController?.abort();
                return;
            }
            sendQuestion(input?.value || "");
        });

        sendButton?.addEventListener("click", (event) => {
            if (!requestInFlight) return;
            event.preventDefault();
            abortController?.abort();
        });

        document.addEventListener("click", async (event) => {
            const promptButton = event.target.closest("[data-prompt]");
            if (promptButton && app.contains(promptButton)) {
                const prompt = promptButton.dataset.prompt || "";
                closeSidebar();
                sendQuestion(prompt);
                return;
            }

            const copyButton = event.target.closest("[data-copy-message]");
            if (copyButton && app.contains(copyButton)) {
                const answerNode = copyButton.closest(".easy-chat-message__content")?.querySelector("[data-answer-text]");
                const text = answerNode?.dataset.rawText || answerNode?.textContent?.trim();
                if (!text) return;
                try {
                    await navigator.clipboard.writeText(text);
                    const label = copyButton.querySelector("span");
                    if (label) label.textContent = "Скопійовано";
                    window.setTimeout(() => { if (label) label.textContent = "Копіювати"; }, 1300);
                } catch {
                    showToast("Не вдалося скопіювати текст");
                }
            }
        });

        thread?.addEventListener("scroll", () => {
            const visible = !nearBottom();
            jump?.classList.toggle("is-visible", visible);
            jump?.setAttribute("aria-hidden", visible ? "false" : "true");
        }, { passive: true });

        jump?.querySelector("button")?.addEventListener("click", () => scrollToBottom("smooth"));

        document.addEventListener("keydown", (event) => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
                event.preventDefault();
                clearConversation();
            }
            if (event.key === "Escape") closeSidebar();
        });
    });
})();
