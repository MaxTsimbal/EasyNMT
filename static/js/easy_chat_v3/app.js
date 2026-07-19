(() => {
    "use strict";

    document.addEventListener("DOMContentLoaded", () => {
        const app = document.getElementById("easyChatV2");
        if (!app || !window.EasyChatV2Storage || !window.EasyChatV2Markdown) return;

        const { EasyChatStore, makeId } = window.EasyChatV2Storage;
        const markdown = window.EasyChatV2Markdown;
        const body = document.body;
        const root = document.documentElement;
        const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

        const config = {
            streamUrl: app.dataset.streamUrl || "",
            fallbackUrl: app.dataset.fallbackUrl || "",
            attachmentUrl: app.dataset.attachmentUrl || "",
            conversationsUrl: app.dataset.conversationsUrl || "",
            feedbackUrlTemplate: app.dataset.feedbackUrlTemplate || "",
            storageKey: app.dataset.storageKey || "easy-chat-v2",
            lessonContext: app.dataset.lessonContext === "true",
            lessonId: app.dataset.lessonId || "",
            lessonTitle: app.dataset.lessonTitle || "",
            subject: app.dataset.subject || "Підготовка до НМТ",
            initialMode: app.dataset.aiMode || "offline",
            initialUsed: Number(app.dataset.aiUsed || 0),
            initialLimit: Number(app.dataset.aiLimit || 0),
            userName: app.dataset.userName || "друже",
        };

        const store = new EasyChatStore(config.storageKey, config);

        const elements = {
            sidebar: document.getElementById("ec2Sidebar"),
            sidebarOpen: document.getElementById("ec2SidebarOpen"),
            sidebarClose: document.getElementById("ec2SidebarClose"),
            sidebarCollapse: document.getElementById("ec2SidebarCollapse"),
            drawerOverlay: document.getElementById("ec2DrawerOverlay"),
            historySearch: document.getElementById("ec2HistorySearch"),
            historyList: document.getElementById("ec2HistoryList"),
            historyEmpty: document.getElementById("ec2HistoryEmpty"),
            newChat: document.getElementById("ec2NewChat"),
            activeTitle: document.getElementById("ec2ActiveTitle"),
            activeSubtitle: document.getElementById("ec2ActiveSubtitle"),
            renameActive: document.getElementById("ec2RenameActive"),
            thread: document.getElementById("ec2Thread"),
            messages: document.getElementById("ec2Messages"),
            welcomeTemplate: document.getElementById("ec2WelcomeTemplate"),
            composer: document.getElementById("ec2Composer"),
            input: document.getElementById("ec2Input"),
            charCount: document.getElementById("ec2CharCount"),
            sendButton: document.getElementById("ec2SendButton"),
            sendHint: document.getElementById("ec2SendHint"),
            jumpBottom: document.getElementById("ec2JumpBottom"),
            commandMenu: document.getElementById("ec2CommandMenu"),
            commandButton: document.getElementById("ec2CommandButton"),
            attachButton: document.getElementById("ec2AttachButton"),
            attachmentInput: document.getElementById("ec2AttachmentInput"),
            attachmentTray: document.getElementById("ec2AttachmentTray"),
            exportChat: document.getElementById("ec2ExportChat"),
            exportSettings: document.getElementById("ec2ExportSettings"),
            settings: document.getElementById("ec2Settings"),
            settingsOpen: document.getElementById("ec2SettingsOpen"),
            settingsClose: document.getElementById("ec2SettingsClose"),
            settingsOverlay: document.getElementById("ec2SettingsOverlay"),
            compactToggle: document.getElementById("ec2CompactSidebarToggle"),
            clearHistory: document.getElementById("ec2ClearHistory"),
            renameDialog: document.getElementById("ec2RenameDialog"),
            renameForm: document.getElementById("ec2RenameForm"),
            renameInput: document.getElementById("ec2RenameInput"),
            deleteDialog: document.getElementById("ec2DeleteDialog"),
            deleteForm: document.getElementById("ec2DeleteForm"),
            toastStack: document.getElementById("ec2ToastStack"),
            serverSeed: document.getElementById("ec2ServerSeed"),
            topStatusDot: document.getElementById("ec2TopStatusDot"),
            sidebarStatusDot: document.getElementById("ec2SidebarStatusDot"),
            topModeLabel: document.getElementById("ec2TopModeLabel"),
            sidebarModeLabel: document.getElementById("ec2SidebarModeLabel"),
            usageLabel: document.getElementById("ec2UsageLabel"),
            usageValue: document.getElementById("ec2UsageValue"),
            usageBar: document.getElementById("ec2UsageBar"),
        };

        const commandPrompts = {
            explain: config.lessonContext
                ? "Поясни цю тему з самого початку простими словами, а потім наведи один зрозумілий приклад."
                : "Поясни тему, яку я назву, з самого початку простими словами, а потім наведи приклад.",
            example: config.lessonContext
                ? "Дай типове завдання НМТ до цієї теми та розв’яжи його крок за кроком."
                : "Дай типове завдання НМТ і розв’яжи його крок за кроком.",
            test: "Проведи коротку перевірку знань. Постав одне запитання, дочекайся моєї відповіді та тільки потім перевір її.",
            mistake: "Допоможи знайти помилку в моєму розв’язанні. Спочатку попроси мене надіслати хід розв’язання.",
        };

        let requestInFlight = false;
        let abortController = null;
        let streamingNode = null;
        let streamedText = "";
        let renameTargetId = null;
        let deleteTargetId = null;
        let deleteScope = "conversation";
        let toastSequence = 0;
        let pendingAttachments = [];
        let attachmentUploadInFlight = false;

        const hideGlobalChrome = () => {
            document.getElementById("pageLoader")?.classList.add("hidden");
            document.getElementById("pageLoader")?.setAttribute("aria-hidden", "true");
            body.classList.remove("easy-transition-loading");
            body.classList.add("ec2-ready");
        };

        let stableViewportHeight = Math.round(window.visualViewport?.height || window.innerHeight);
        let viewportFrame = 0;

        const isEditableFocused = () => {
            const active = document.activeElement;
            return active === elements.input || active === elements.renameInput || active?.matches?.("input, textarea, [contenteditable='true']");
        };

        const syncViewport = () => {
            const viewport = window.visualViewport;
            const height = Math.max(320, Math.round(viewport?.height || window.innerHeight));
            const offsetTop = Math.max(0, Math.round(viewport?.offsetTop || 0));
            const focused = isEditableFocused();

            if (!focused && height > stableViewportHeight * .82) {
                stableViewportHeight = Math.max(stableViewportHeight, height);
            }

            const keyboardHeight = focused ? Math.max(0, stableViewportHeight - height) : 0;
            const keyboardOpen = focused && keyboardHeight > 90;

            root.style.setProperty("--ec2-app-height", `${height}px`);
            root.style.setProperty("--ec2-viewport-top", `${offsetTop}px`);
            root.style.setProperty("--ec3-keyboard-height", `${keyboardHeight}px`);
            body.classList.toggle("ec3-keyboard-open", keyboardOpen);
        };

        const scheduleViewportSync = () => {
            window.cancelAnimationFrame(viewportFrame);
            viewportFrame = window.requestAnimationFrame(syncViewport);
        };

        const showToast = (message, type = "info") => {
            if (!elements.toastStack || !message) return;
            const toast = document.createElement("div");
            toast.className = `ec2-toast ec2-toast--${type}`;
            toast.dataset.toastId = String(++toastSequence);
            toast.innerHTML = `<span aria-hidden="true">${type === "success" ? "✓" : type === "error" ? "!" : "✦"}</span><p>${markdown.escapeHtml(message)}</p>`;
            elements.toastStack.appendChild(toast);
            requestAnimationFrame(() => toast.classList.add("is-visible"));
            window.setTimeout(() => {
                toast.classList.remove("is-visible");
                window.setTimeout(() => toast.remove(), 240);
            }, 2600);
        };

        const serverJson = async (url, options = {}) => {
            if (!url) return null;
            try {
                const response = await fetch(url, {
                    credentials: "same-origin",
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                        ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
                        ...(options.headers || {}),
                    },
                    ...options,
                });
                const data = await response.json().catch(() => null);
                if (!response.ok || (data && data.ok === false)) throw new Error(data?.error || `Помилка ${response.status}`);
                return data;
            } catch (error) {
                console.warn("EasyNMT server sync failed:", error);
                return null;
            }
        };

        const formatFileSize = (bytes) => {
            const size = Number(bytes) || 0;
            if (size < 1024) return `${size} Б`;
            if (size < 1024 * 1024) return `${Math.round(size / 1024)} КБ`;
            return `${(size / (1024 * 1024)).toFixed(1)} МБ`;
        };

        const renderAttachmentTray = () => {
            if (!elements.attachmentTray) return;
            elements.attachmentTray.hidden = pendingAttachments.length === 0 && !attachmentUploadInFlight;
            elements.attachmentTray.innerHTML = pendingAttachments.map((attachment) => `
                <div class="ec2-attachment-chip" data-attachment-id="${markdown.escapeHtml(attachment.id)}">
                    <span class="ec2-attachment-chip__icon" aria-hidden="true">▧</span>
                    <span class="ec2-attachment-chip__copy"><b>${markdown.escapeHtml(attachment.name || "Фото")}</b><small>${formatFileSize(attachment.size_bytes)}</small></span>
                    <button type="button" data-remove-attachment="${markdown.escapeHtml(attachment.id)}" aria-label="Прибрати фото">×</button>
                </div>
            `).join("") + (attachmentUploadInFlight ? `
                <div class="ec2-attachment-chip is-loading"><span class="ec2-attachment-chip__loader" aria-hidden="true"></span><span class="ec2-attachment-chip__copy"><b>Завантажую фото</b><small>Готую до аналізу</small></span></div>
            ` : "");
            updateInputState();
        };

        const uploadAttachment = async (file) => {
            if (!file || attachmentUploadInFlight) return;
            if (pendingAttachments.length >= 3) {
                showToast("Можна додати до трьох фото", "info");
                return;
            }
            if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
                showToast("Підтримуються PNG, JPG і WEBP", "error");
                return;
            }
            if (file.size > 5 * 1024 * 1024) {
                showToast("Фото завелике. Максимум 5 МБ", "error");
                return;
            }
            attachmentUploadInFlight = true;
            renderAttachmentTray();
            const formData = new FormData();
            formData.append("file", file);
            formData.append("conversation_id", store.state.activeId || "");
            const data = await serverJson(config.attachmentUrl, { method: "POST", body: formData });
            attachmentUploadInFlight = false;
            if (data?.attachment) {
                pendingAttachments.push(data.attachment);
                showToast("Фото додано до запиту", "success");
            } else {
                showToast("Не вдалося завантажити фото", "error");
            }
            if (elements.attachmentInput) elements.attachmentInput.value = "";
            renderAttachmentTray();
        };

        const clearPendingAttachments = () => {
            pendingAttachments = [];
            attachmentUploadInFlight = false;
            renderAttachmentTray();
        };

        const isNearBottom = () => {
            if (!elements.thread) return true;
            return elements.thread.scrollHeight - elements.thread.scrollTop - elements.thread.clientHeight < 140;
        };

        const scrollToBottom = (behavior = "auto") => {
            if (!elements.thread) return;
            elements.thread.scrollTo({ top: elements.thread.scrollHeight, behavior: reduceMotion ? "auto" : behavior });
        };

        const openSidebar = () => {
            body.classList.add("ec2-drawer-open");
            elements.sidebar?.classList.add("is-open");
            elements.drawerOverlay?.classList.add("is-visible");
        };

        const closeSidebar = () => {
            body.classList.remove("ec2-drawer-open");
            elements.sidebar?.classList.remove("is-open");
            elements.drawerOverlay?.classList.remove("is-visible");
        };

        const openSettings = () => {
            closeSidebar();
            elements.settings?.classList.add("is-open");
            elements.settings?.setAttribute("aria-hidden", "false");
            elements.settingsOverlay?.classList.add("is-visible");
            body.classList.add("ec2-settings-open");
        };

        const closeSettings = () => {
            elements.settings?.classList.remove("is-open");
            elements.settings?.setAttribute("aria-hidden", "true");
            elements.settingsOverlay?.classList.remove("is-visible");
            body.classList.remove("ec2-settings-open");
        };

        const setCompactSidebar = (value, persist = true) => {
            const compact = Boolean(value);
            body.classList.toggle("ec2-sidebar-compact", compact);
            if (elements.compactToggle) elements.compactToggle.checked = compact;
            elements.sidebarCollapse?.setAttribute("aria-label", compact ? "Розгорнути бокову панель" : "Згорнути бокову панель");
            if (persist) store.setPreference("compactSidebar", compact);
        };

        const modeLabels = {
            explain: { title: "Пояснення", description: "Детально, спокійно, з прикладом" },
            concise: { title: "Коротко", description: "Стисло та лише по суті" },
            practice: { title: "Практика", description: "Запитання, підказки та перевірка" },
        };

        const setResponseMode = (mode, persist = true) => {
            const normalized = Object.prototype.hasOwnProperty.call(modeLabels, mode) ? mode : "explain";
            app.dataset.responseMode = normalized;
            document.querySelectorAll("[data-response-mode]").forEach((button) => {
                button.classList.toggle("is-active", button.dataset.responseMode === normalized);
            });
            document.querySelectorAll("[data-settings-mode]").forEach((button) => {
                button.classList.toggle("is-active", button.dataset.settingsMode === normalized);
            });
            if (persist) store.setPreference("responseMode", normalized);
        };

        const updateAiMode = ({ mode = config.initialMode, used = config.initialUsed, limit = config.initialLimit } = {}) => {
            const normalized = ["openai", "limit", "offline"].includes(mode) ? mode : "offline";
            const label = normalized === "openai" ? "Easy онлайн" : normalized === "limit" ? "Ліміт вичерпано" : "Локальні матеріали";
            const shortLabel = normalized === "openai" ? "Online" : normalized === "limit" ? "Limit" : "Offline";

            [elements.topStatusDot, elements.sidebarStatusDot].forEach((dot) => {
                if (!dot) return;
                dot.classList.remove("ec2-status-dot--openai", "ec2-status-dot--limit", "ec2-status-dot--offline");
                dot.classList.add(`ec2-status-dot--${normalized}`);
            });
            if (elements.topModeLabel) elements.topModeLabel.textContent = shortLabel;
            if (elements.sidebarModeLabel) elements.sidebarModeLabel.textContent = label;

            const numericLimit = Math.max(0, Number(limit) || 0);
            const numericUsed = Math.max(0, Number(used) || 0);
            const percent = numericLimit ? Math.min(100, Math.round((numericUsed / numericLimit) * 100)) : 0;
            if (elements.usageLabel) elements.usageLabel.textContent = `${numericUsed} з ${numericLimit} запитів`;
            if (elements.usageValue) elements.usageValue.textContent = `${percent}%`;
            if (elements.usageBar) elements.usageBar.style.width = `${percent}%`;
        };

        const groupLabel = (isoDate, pinned = false) => {
            if (pinned) return "Закріплені";
            const date = new Date(isoDate);
            const today = new Date();
            const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
            const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
            const diffDays = Math.round((startToday - startDate) / 86400000);
            if (diffDays <= 0) return "Сьогодні";
            if (diffDays === 1) return "Учора";
            if (diffDays <= 7) return "Останні 7 днів";
            return "Раніше";
        };

        const historyIcon = (conversation) => conversation.context?.lessonContext
            ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4.5h14v15H5zM8 8h8M8 12h8M8 16h5"/></svg>'
            : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.5 5h11A2.5 2.5 0 0 1 20 7.5v7a2.5 2.5 0 0 1-2.5 2.5H11l-5 3v-4.2A2.5 2.5 0 0 1 4 13.35V7.5A2.5 2.5 0 0 1 6.5 5Z"/></svg>';

        const renderHistory = () => {
            if (!elements.historyList) return;
            const search = String(elements.historySearch?.value || "").trim().toLocaleLowerCase("uk-UA");
            const conversations = store.list().filter((conversation) => {
                if (!search) return true;
                const haystack = `${conversation.title} ${conversation.context?.lessonTitle || ""} ${conversation.messages.map((item) => item.text).join(" ")}`.toLocaleLowerCase("uk-UA");
                return haystack.includes(search);
            });

            elements.historyList.innerHTML = "";
            if (elements.historyEmpty) elements.historyEmpty.hidden = conversations.length > 0;

            let activeGroup = "";
            conversations.forEach((conversation) => {
                const label = groupLabel(conversation.updatedAt, conversation.pinned);
                if (label !== activeGroup) {
                    activeGroup = label;
                    const heading = document.createElement("div");
                    heading.className = "ec2-history-group";
                    heading.textContent = label;
                    elements.historyList.appendChild(heading);
                }

                const item = document.createElement("div");
                item.className = "ec2-history-item";
                item.dataset.conversationId = conversation.id;
                item.classList.toggle("is-active", conversation.id === store.state.activeId);
                item.innerHTML = `
                    <button class="ec2-history-item__main" type="button" data-open-conversation="${markdown.escapeHtml(conversation.id)}">
                        <span class="ec2-history-item__icon">${historyIcon(conversation)}</span>
                        <span class="ec2-history-item__copy">
                            <strong>${markdown.escapeHtml(conversation.title)}</strong>
                            <small>${markdown.escapeHtml(conversation.context?.lessonTitle || conversation.context?.subject || "Загальний чат")}</small>
                        </span>
                        ${conversation.pinned ? '<span class="ec2-history-item__pin" title="Закріплено">◆</span>' : ""}
                    </button>
                    <button class="ec2-history-item__more" type="button" data-history-menu="${markdown.escapeHtml(conversation.id)}" aria-label="Дії з розмовою">
                        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></svg>
                    </button>
                    <div class="ec2-history-popover" data-history-popover="${markdown.escapeHtml(conversation.id)}">
                        <button type="button" data-history-action="rename" data-id="${markdown.escapeHtml(conversation.id)}"><span>✎</span> Перейменувати</button>
                        <button type="button" data-history-action="pin" data-id="${markdown.escapeHtml(conversation.id)}"><span>◆</span> ${conversation.pinned ? "Відкріпити" : "Закріпити"}</button>
                        <button type="button" data-history-action="export" data-id="${markdown.escapeHtml(conversation.id)}"><span>⇩</span> Експортувати</button>
                        <button type="button" class="is-danger" data-history-action="delete" data-id="${markdown.escapeHtml(conversation.id)}"><span>×</span> Видалити</button>
                    </div>`;
                elements.historyList.appendChild(item);
            });
        };

        const closeHistoryPopovers = (exceptId = null) => {
            document.querySelectorAll("[data-history-popover]").forEach((popover) => {
                const keep = exceptId && popover.dataset.historyPopover === exceptId;
                popover.classList.toggle("is-open", Boolean(keep));
            });
        };

        const createUserMessageNode = (message) => {
            const article = document.createElement("article");
            article.className = "ec2-message ec2-message--user";
            article.dataset.messageId = message.id;
            article.dataset.role = "user";
            article.innerHTML = `
                <div class="ec2-message__rail">
                    <span class="ec2-message__user-avatar">${markdown.escapeHtml(config.userName.charAt(0).toUpperCase() || "Т")}</span>
                </div>
                <div class="ec2-message__column">
                    <div class="ec2-message__meta"><strong>Ти</strong><time>${new Date(message.createdAt).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</time></div>
                    <div class="ec2-user-bubble" data-raw-text="${markdown.escapeHtml(message.text)}">${markdown.escapeHtml(message.text).replace(/\n/g, "<br>")}</div>
                    <div class="ec2-message__actions ec2-message__actions--user">
                        <button type="button" data-message-action="copy" aria-label="Копіювати повідомлення"><svg viewBox="0 0 24 24"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg></button>
                    </div>
                </div>`;
            return article;
        };

        const assistantActionsHtml = (message) => `
            <div class="ec2-message__actions">
                <button type="button" data-message-action="copy" title="Копіювати">
                    <svg viewBox="0 0 24 24"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg><span>Копіювати</span>
                </button>
                <button type="button" data-message-action="regenerate" title="Створити іншу відповідь">
                    <svg viewBox="0 0 24 24"><path d="M19 8V4l-2 2a8 8 0 1 0 2.2 8"/></svg><span>Ще раз</span>
                </button>
                <span class="ec2-action-divider"></span>
                <button class="ec2-feedback-button ${message.feedback === "up" ? "is-active" : ""}" type="button" data-message-action="feedback-up" title="Корисна відповідь" aria-label="Корисна відповідь">
                    <svg viewBox="0 0 24 24"><path d="M7 21H4V9h3m0 12h9.5a2 2 0 0 0 1.9-1.4l2.2-7A2 2 0 0 0 18.7 10H14l.7-3.4A3 3 0 0 0 12 3l-5 6z"/></svg>
                </button>
                <button class="ec2-feedback-button ${message.feedback === "down" ? "is-active" : ""}" type="button" data-message-action="feedback-down" title="Потрібно краще" aria-label="Потрібно краще">
                    <svg viewBox="0 0 24 24"><path d="M7 3H4v12h3M7 3h9.5a2 2 0 0 1 1.9 1.4l2.2 7a2 2 0 0 1-1.9 2.6H14l.7 3.4A3 3 0 0 1 12 21l-5-6z"/></svg>
                </button>
            </div>`;

        const createAssistantMessageNode = (message, { pending = false } = {}) => {
            const article = document.createElement("article");
            article.className = `ec2-message ec2-message--assistant${pending ? " is-pending" : ""}`;
            article.dataset.messageId = message.id;
            article.dataset.role = "assistant";
            article.innerHTML = `
                <div class="ec2-message__rail">
                    <span class="ec2-message__easy-avatar"><img src="/static/images/easynmt-mascot.png" alt=""></span>
                    <span class="ec2-message__rail-line"></span>
                </div>
                <div class="ec2-message__column">
                    <div class="ec2-message__meta"><strong>Easy</strong><span>AI-викладач</span><time>${new Date(message.createdAt || Date.now()).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</time></div>
                    <div class="ec2-assistant-card">
                        <div class="ec2-thinking" ${pending ? "" : "hidden"}>
                            <span class="ec2-thinking__mark" aria-hidden="true">✦</span>
                            <span class="ec2-thinking__copy"><strong>Easy думає</strong><small data-thinking-status>Будую зрозумілу відповідь</small></span>
                            <span class="ec2-thinking__dots" aria-hidden="true"><i></i><i></i><i></i></span>
                        </div>
                        <div class="ec2-answer ${pending ? "" : "is-ready"}" data-answer-content data-raw-text="${markdown.escapeHtml(message.text || "")}"></div>
                    </div>
                    <div data-assistant-actions>${pending ? "" : assistantActionsHtml(message)}</div>
                </div>`;

            const answer = article.querySelector("[data-answer-content]");
            if (!pending && answer) {
                answer.innerHTML = markdown.render(message.text);
                markdown.typesetMath(answer);
            }
            return article;
        };

        const renderWelcome = () => {
            if (!elements.messages || !elements.welcomeTemplate) return;
            elements.messages.appendChild(elements.welcomeTemplate.content.cloneNode(true));
        };

        const renderConversation = ({ preserveScroll = false } = {}) => {
            if (!elements.messages) return;
            const conversation = store.getActive();
            const previousBottomDistance = elements.thread
                ? elements.thread.scrollHeight - elements.thread.scrollTop
                : 0;

            elements.messages.innerHTML = "";
            if (!conversation.messages.length) {
                renderWelcome();
            } else {
                conversation.messages.forEach((message) => {
                    const node = message.role === "user"
                        ? createUserMessageNode(message)
                        : createAssistantMessageNode(message);
                    elements.messages.appendChild(node);
                });
            }

            if (elements.activeTitle) elements.activeTitle.textContent = conversation.title;
            if (elements.activeSubtitle) {
                const messageCount = conversation.messages.length;
                elements.activeSubtitle.textContent = messageCount
                    ? `${Math.ceil(messageCount / 2)} ${messageCount <= 2 ? "відповідь" : "повідомлень"}`
                    : (conversation.context?.lessonTitle || "AI Викладач");
            }
            renderHistory();

            requestAnimationFrame(() => {
                if (preserveScroll && elements.thread) {
                    elements.thread.scrollTop = Math.max(0, elements.thread.scrollHeight - previousBottomDistance);
                } else {
                    scrollToBottom();
                }
            });
        };

        const appendMessageNode = (message) => {
            elements.messages?.querySelector(".ec2-welcome")?.remove();
            const node = message.role === "user"
                ? createUserMessageNode(message)
                : createAssistantMessageNode(message);
            elements.messages?.appendChild(node);
            return node;
        };

        const createPendingAssistant = (messageId = makeId("stream")) => {
            const message = { id: messageId, role: "assistant", text: "", createdAt: new Date().toISOString(), feedback: null };
            const node = createAssistantMessageNode(message, { pending: true });
            elements.messages?.appendChild(node);
            return node;
        };

        const updateInputState = () => {
            const input = elements.input;
            if (!input) return;
            input.style.height = "auto";
            const mobileComposer = window.matchMedia("(max-width: 720px)").matches;
            const maxHeight = mobileComposer ? 118 : 188;
            const minHeight = mobileComposer ? 40 : 26;
            input.style.height = `${Math.min(maxHeight, Math.max(minHeight, input.scrollHeight))}px`;
            const length = input.value.length;
            if (elements.charCount) {
                elements.charCount.textContent = `${length} / 1500`;
                elements.charCount.classList.toggle("is-visible", length > 900);
                elements.charCount.classList.toggle("is-warning", length > 1380);
            }
            if (elements.sendButton) elements.sendButton.disabled = !requestInFlight && !input.value.trim() && pendingAttachments.length === 0;
            updateCommandMenuFromInput();
        };

        const setBusy = (value) => {
            requestInFlight = Boolean(value);
            app.classList.toggle("is-generating", requestInFlight);
            elements.thread?.setAttribute("aria-busy", requestInFlight ? "true" : "false");
            elements.composer?.classList.toggle("is-generating", requestInFlight);
            if (elements.sendButton) {
                elements.sendButton.disabled = !requestInFlight && !elements.input?.value.trim();
                elements.sendButton.setAttribute("aria-label", requestInFlight ? "Зупинити відповідь" : "Надіслати повідомлення");
            }
            if (elements.sendHint) elements.sendHint.textContent = requestInFlight ? "Stop" : "Enter";
        };

        const setThinkingStatus = (node, text) => {
            const status = node?.querySelector("[data-thinking-status]");
            if (status && text) status.textContent = text;
        };

        const startStreamingVisual = (node) => {
            if (!node) return null;
            node.classList.remove("is-pending");
            node.classList.add("is-streaming");
            node.querySelector(".ec2-thinking")?.setAttribute("hidden", "");
            const answer = node.querySelector("[data-answer-content]");
            answer?.classList.add("is-streaming");
            return answer;
        };

        const finishStreamingVisual = async (node, text, message) => {
            if (!node) return;
            node.classList.remove("is-pending", "is-streaming");
            const thinking = node.querySelector(".ec2-thinking");
            thinking?.setAttribute("hidden", "");
            const answer = node.querySelector("[data-answer-content]");
            if (answer) {
                answer.classList.remove("is-streaming");
                answer.classList.add("is-ready");
                answer.dataset.rawText = text;
                answer.innerHTML = markdown.render(text);
                await markdown.typesetMath(answer);
            }
            const actionHost = node.querySelector("[data-assistant-actions]");
            if (actionHost && message) actionHost.innerHTML = assistantActionsHtml(message);
        };

        const appendStreamDelta = (answerNode, delta) => {
            if (!answerNode || !delta) return;
            streamedText += delta;
            answerNode.dataset.rawText = streamedText;
            answerNode.textContent = streamedText;
            if (isNearBottom()) scrollToBottom();
        };

        const readSseStream = async (response, handlers = {}) => {
            if (!response.body) throw new Error("Браузер не підтримує потокову відповідь.");
            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";

            const emitBlock = (block) => {
                if (!block.trim()) return;
                let eventName = "message";
                const dataLines = [];
                block.split(/\r?\n/).forEach((line) => {
                    if (line.startsWith("event:")) eventName = line.slice(6).trim();
                    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
                });
                const rawData = dataLines.join("\n");
                let payload = rawData;
                try { payload = JSON.parse(rawData); } catch { /* Plain string events are valid. */ }
                handlers.onEvent?.(eventName, payload);
            };

            while (true) {
                const { value, done } = await reader.read();
                buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
                const blocks = buffer.split(/\r?\n\r?\n/);
                buffer = blocks.pop() || "";
                blocks.forEach(emitBlock);
                if (done) break;
            }
            if (buffer.trim()) emitBlock(buffer);
        };

        const simulateTyping = async (answerNode, text) => {
            streamedText = "";
            if (reduceMotion || text.length > 5000) {
                appendStreamDelta(answerNode, text);
                return;
            }
            const tokens = text.match(/\S+\s*/g) || [text];
            for (const token of tokens) {
                if (abortController?.signal.aborted) throw new DOMException("Aborted", "AbortError");
                appendStreamDelta(answerNode, token);
                const delay = /[.!?]\s*$/.test(token) ? 45 : /[,;:]\s*$/.test(token) ? 24 : 11;
                await new Promise((resolve) => window.setTimeout(resolve, delay));
            }
        };

        const collectHistory = (conversation) => conversation.messages.slice(-12).map((message) => ({
            role: message.role,
            text: message.text.slice(0, 1800),
        }));

        const requestPayload = (question, history, identifiers = {}) => ({
            question,
            context: config.lessonContext ? "lesson" : "general",
            lesson_id: config.lessonId,
            history,
            response_mode: app.dataset.responseMode || "explain",
            conversation_id: store.state.activeId,
            user_message_id: identifiers.userMessageId || makeId("msg-user"),
            assistant_message_id: identifiers.assistantMessageId || makeId("msg-easy"),
            attachment_ids: Array.isArray(identifiers.attachmentIds) ? identifiers.attachmentIds : [],
        });

        const requestJsonFallback = async (payload, signal) => {
            const response = await fetch(config.fallbackUrl, {
                method: "POST",
                credentials: "same-origin",
                signal,
                headers: {
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: JSON.stringify(payload),
            });
            const data = await response.json().catch(() => null);
            if (!response.ok || !data?.ok) throw new Error(data?.error || `Помилка ${response.status}`);
            return data;
        };

        const sendQuestion = async (rawQuestion, options = {}) => {
            const typedQuestion = String(rawQuestion || "").trim();
            const question = typedQuestion || (pendingAttachments.length ? "Допоможи розібрати це фото крок за кроком і знайди місце, яке треба перевірити." : "");
            if (!question || requestInFlight || attachmentUploadInFlight || !elements.messages) return;

            const activeConversationId = store.state.activeId;
            const conversation = store.getActive();
            let historyBeforeQuestion = collectHistory(conversation);
            if (options.appendUser === false) {
                const lastMessage = conversation.messages.at(-1);
                if (lastMessage?.role === "user" && lastMessage.text.trim() === question) {
                    historyBeforeQuestion = historyBeforeQuestion.slice(0, -1);
                }
            }
            closeCommandMenu();
            closeSidebar();

            let userMessage = null;
            if (options.appendUser !== false) {
                userMessage = store.addMessage("user", question, activeConversationId);
                if (userMessage) appendMessageNode(userMessage);
                renderHistory();
            } else {
                userMessage = [...conversation.messages].reverse().find((message) => message.role === "user" && message.text.trim() === question) || null;
            }

            const assistantMessageId = makeId("msg-easy");
            const attachmentIds = pendingAttachments.map((attachment) => attachment.id);
            const pendingNode = createPendingAssistant(assistantMessageId);
            streamingNode = pendingNode;
            streamedText = "";
            scrollToBottom("smooth");

            if (elements.input) {
                elements.input.value = "";
                updateInputState();
            }

            abortController = new AbortController();
            setBusy(true);
            const payload = requestPayload(question, historyBeforeQuestion, {
                userMessageId: userMessage?.id || makeId("msg-user"),
                assistantMessageId,
                attachmentIds,
            });
            clearPendingAttachments();
            let finalMeta = null;

            try {
                if (!config.streamUrl) throw new Error("stream-unavailable");
                const response = await fetch(config.streamUrl, {
                    method: "POST",
                    credentials: "same-origin",
                    signal: abortController.signal,
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    body: JSON.stringify(payload),
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => null);
                    throw new Error(errorData?.error || `Помилка ${response.status}`);
                }

                const contentType = response.headers.get("content-type") || "";
                if (!contentType.includes("text/event-stream")) throw new Error("stream-unavailable");

                let answerNode = pendingNode.querySelector("[data-answer-content]");
                await readSseStream(response, {
                    onEvent: (eventName, data) => {
                        if (eventName === "status") {
                            setThinkingStatus(pendingNode, data?.message || "Аналізую запит");
                        } else if (eventName === "meta") {
                            finalMeta = data || finalMeta;
                            updateAiMode(data || {});
                        } else if (eventName === "delta") {
                            if (!streamedText) answerNode = startStreamingVisual(pendingNode) || answerNode;
                            appendStreamDelta(answerNode, typeof data === "string" ? data : data?.text || "");
                        } else if (eventName === "done") {
                            finalMeta = { ...(finalMeta || {}), ...(data || {}) };
                            if (!streamedText && data?.answer) {
                                answerNode = startStreamingVisual(pendingNode) || answerNode;
                                appendStreamDelta(answerNode, data.answer);
                            }
                        } else if (eventName === "error") {
                            throw new Error(data?.error || "Easy не зміг сформувати відповідь.");
                        }
                    },
                });
            } catch (error) {
                if (error.name === "AbortError") {
                    if (streamedText.trim()) {
                        showToast("Відповідь зупинено", "info");
                    } else {
                        pendingNode.remove();
                        showToast("Генерацію зупинено", "info");
                        return;
                    }
                } else if (error.message === "stream-unavailable" || /потокову/.test(error.message) || error instanceof TypeError) {
                    try {
                        setThinkingStatus(pendingNode, "Готую відповідь");
                        const data = await requestJsonFallback(payload, abortController.signal);
                        finalMeta = data;
                        updateAiMode(data);
                        const answerNode = startStreamingVisual(pendingNode);
                        await simulateTyping(answerNode, String(data.answer || ""));
                    } catch (fallbackError) {
                        if (fallbackError.name === "AbortError") {
                            pendingNode.remove();
                            showToast("Генерацію зупинено", "info");
                            return;
                        }
                        pendingNode.remove();
                        const fallbackMessage = {
                            id: makeId("error"),
                            role: "assistant",
                            text: `Не вдалося отримати відповідь. ${fallbackError.message || "Перевір з’єднання та спробуй ще раз."}`,
                            createdAt: new Date().toISOString(),
                            feedback: null,
                        };
                        const fallbackNode = createAssistantMessageNode(fallbackMessage);
                        fallbackNode.classList.add("is-error");
                        elements.messages.appendChild(fallbackNode);
                        showToast("Сталася помилка запиту", "error");
                        return;
                    }
                } else {
                    pendingNode.remove();
                    const errorMessage = {
                        id: makeId("error"),
                        role: "assistant",
                        text: `Не вдалося отримати відповідь. ${error.message || "Перевір з’єднання та спробуй ще раз."}`,
                        createdAt: new Date().toISOString(),
                        feedback: null,
                    };
                    const errorNode = createAssistantMessageNode(errorMessage);
                    errorNode.classList.add("is-error");
                    elements.messages.appendChild(errorNode);
                    showToast("Сталася помилка запиту", "error");
                    console.error("AI Teacher request failed:", error);
                    return;
                }
            } finally {
                if (pendingNode.isConnected && streamedText.trim()) {
                    const persistedAssistantId = finalMeta?.assistant_message_id || assistantMessageId;
                    const savedMessage = store.addMessage("assistant", streamedText.trim(), activeConversationId, { id: persistedAssistantId });
                    if (savedMessage) {
                        pendingNode.dataset.messageId = savedMessage.id;
                        await finishStreamingVisual(pendingNode, savedMessage.text, savedMessage);
                    }
                    if (finalMeta) updateAiMode(finalMeta);
                    renderHistory();
                }
                abortController = null;
                streamingNode = null;
                streamedText = "";
                setBusy(false);
                updateInputState();
                scrollToBottom();
                const shouldRestoreFocus = !window.matchMedia("(max-width: 720px)").matches || document.activeElement === elements.input;
                if (shouldRestoreFocus) window.setTimeout(() => elements.input?.focus({ preventScroll: true }), 80);
            }
        };

        const stopGeneration = () => {
            if (!requestInFlight) return;
            abortController?.abort();
        };

        const openRenameDialog = (conversationId) => {
            const conversation = store.getConversation(conversationId);
            if (!conversation) return;
            renameTargetId = conversationId;
            document.activeElement?.blur?.();
            if (elements.renameInput) elements.renameInput.value = conversation.title;
            if (elements.renameDialog?.showModal) {
                body.classList.add("ec3-dialog-open");
                elements.renameDialog.showModal();
                window.setTimeout(() => {
                    elements.renameInput?.focus({ preventScroll: true });
                    elements.renameInput?.select();
                    scheduleViewportSync();
                }, 80);
            }
        };

        const openDeleteDialog = (conversationId = null, scope = "conversation") => {
            deleteTargetId = conversationId;
            deleteScope = scope;
            const title = elements.deleteDialog?.querySelector("h2");
            const description = elements.deleteDialog?.querySelector("p");
            if (title) title.textContent = scope === "all" ? "Очистити всю історію?" : "Видалити розмову?";
            if (description) description.textContent = scope === "all"
                ? "Усі розмови на цьому пристрої буде видалено. Цю дію не можна скасувати."
                : "Цю дію не можна буде скасувати.";
            document.activeElement?.blur?.();
            body.classList.add("ec3-dialog-open");
            elements.deleteDialog?.showModal?.();
            window.setTimeout(scheduleViewportSync, 30);
        };

        const exportConversation = (conversationId = store.state.activeId) => {
            const conversation = store.getConversation(conversationId);
            const content = store.exportConversation(conversationId);
            if (!conversation || !content) {
                showToast("У цій розмові поки немає повідомлень", "info");
                return;
            }
            const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement("a");
            anchor.href = url;
            anchor.download = `${conversation.title.replace(/[\\/:*?"<>|]/g, "").slice(0, 60) || "easy-chat"}.md`;
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            URL.revokeObjectURL(url);
            showToast("Розмову експортовано", "success");
        };

        const copyText = async (text, successMessage = "Скопійовано") => {
            if (!text) return;
            try {
                await navigator.clipboard.writeText(text);
                showToast(successMessage, "success");
            } catch {
                const area = document.createElement("textarea");
                area.value = text;
                area.style.position = "fixed";
                area.style.opacity = "0";
                document.body.appendChild(area);
                area.select();
                document.execCommand("copy");
                area.remove();
                showToast(successMessage, "success");
            }
        };

        const regenerate = async (assistantMessageId) => {
            if (requestInFlight) return;
            const conversation = store.getActive();
            const assistantIndex = conversation.messages.findIndex((message) => message.id === assistantMessageId && message.role === "assistant");
            if (assistantIndex < 0) return;
            let userMessage = null;
            for (let index = assistantIndex - 1; index >= 0; index -= 1) {
                if (conversation.messages[index].role === "user") {
                    userMessage = conversation.messages[index];
                    break;
                }
            }
            if (!userMessage) return;
            store.removeMessage(assistantMessageId);
            renderConversation();
            await sendQuestion(userMessage.text, { appendUser: false });
        };

        const handleFeedback = async (messageId, direction) => {
            const conversation = store.getActive();
            const message = conversation.messages.find((item) => item.id === messageId);
            if (!message) return;
            const next = message.feedback === direction ? null : direction;
            store.updateMessage(messageId, { feedback: next });
            const node = elements.messages?.querySelector(`[data-message-id="${CSS.escape(messageId)}"]`);
            node?.querySelectorAll(".ec2-feedback-button").forEach((button) => button.classList.remove("is-active"));
            if (next) node?.querySelector(`[data-message-action="feedback-${next}"]`)?.classList.add("is-active");
            if (next) {
                const feedbackUrl = config.feedbackUrlTemplate.replace("MESSAGE_ID", encodeURIComponent(messageId));
                await serverJson(feedbackUrl, { method: "POST", body: JSON.stringify({ rating: next }) });
                showToast(direction === "up" ? "Дякую за оцінку" : "Врахуємо це в наступних відповідях", "success");
            }
        };

        const closeCommandMenu = () => {
            if (!elements.commandMenu) return;
            elements.commandMenu.hidden = true;
            elements.commandMenu.classList.remove("is-open");
        };

        const openCommandMenu = () => {
            if (!elements.commandMenu) return;
            elements.commandMenu.hidden = false;
            requestAnimationFrame(() => elements.commandMenu?.classList.add("is-open"));
        };

        const updateCommandMenuFromInput = () => {
            const value = elements.input?.value.trimStart() || "";
            if (value === "/" || /^\/[a-z]*$/i.test(value)) openCommandMenu();
            else if (!elements.commandButton?.classList.contains("is-active")) closeCommandMenu();
        };

        const chooseCommand = (command) => {
            const prompt = commandPrompts[command];
            if (!prompt || !elements.input) return;
            elements.input.value = prompt;
            elements.commandButton?.classList.remove("is-active");
            closeCommandMenu();
            updateInputState();
            elements.input.focus();
            elements.input.setSelectionRange(prompt.length, prompt.length);
        };

        const newConversation = () => {
            stopGeneration();
            clearPendingAttachments();
            store.createConversation();
            renderConversation();
            closeSidebar();
            closeSettings();
            if (elements.input) elements.input.value = "";
            updateInputState();
            window.setTimeout(() => elements.input?.focus({ preventScroll: true }), 80);
        };

        const hydrateServerHistory = async () => {
            const data = await serverJson(config.conversationsUrl);
            if (!data?.conversations?.length) return;
            let changed = false;
            data.conversations.forEach((remote) => {
                if (!remote?.id) return;
                const existing = store.getConversation(remote.id);
                const remoteMessages = Array.isArray(remote.messages) ? remote.messages : [];
                if (existing) {
                    const byId = new Map(existing.messages.map((message) => [message.id, message]));
                    remoteMessages.forEach((message) => {
                        if (!message?.id || byId.has(message.id)) return;
                        const normalized = store.normalizeMessage({
                            id: message.id,
                            role: message.role,
                            text: message.text,
                            createdAt: message.createdAt || remote.updated_at,
                        });
                        if (normalized) {
                            existing.messages.push(normalized);
                            byId.set(normalized.id, normalized);
                            changed = true;
                        }
                    });
                    existing.messages.sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
                    if (remote.title && existing.title === "Нова розмова") existing.title = remote.title;
                    existing.pinned = Boolean(remote.pinned || existing.pinned);
                    existing.updatedAt = remote.updated_at || existing.updatedAt;
                } else {
                    const normalized = store.normalizeConversation({
                        id: remote.id,
                        title: remote.title,
                        pinned: remote.pinned,
                        createdAt: remote.created_at,
                        updatedAt: remote.updated_at,
                        context: {
                            lessonContext: Boolean(remote.lesson_id),
                            lessonId: remote.lesson_id || "",
                            lessonTitle: "",
                            subject: remote.subject || config.subject,
                        },
                        messages: remoteMessages.map((message) => ({
                            id: message.id,
                            role: message.role,
                            text: message.text,
                            createdAt: message.createdAt || remote.updated_at,
                        })),
                    });
                    if (normalized) {
                        store.state.conversations.push(normalized);
                        changed = true;
                    }
                }
            });
            if (changed) {
                store.save();
                renderConversation({ preserveScroll: true });
            }
        };

        const importServerSeed = () => {
            const active = store.getActive();
            if (active.messages.length || !elements.serverSeed?.textContent) return;
            try {
                const seed = JSON.parse(elements.serverSeed.textContent);
                const messages = [];
                if (String(seed.question || "").trim()) messages.push({ role: "user", text: seed.question });
                if (String(seed.answer || "").trim()) messages.push({ role: "assistant", text: seed.answer });
                if (messages.length) store.replaceMessages(messages);
            } catch {
                /* The normal GET route has no seed. */
            }
        };

        hideGlobalChrome();
        syncViewport();
        importServerSeed();
        setResponseMode(store.getPreference("responseMode", "explain"), false);
        setCompactSidebar(store.getPreference("compactSidebar", false), false);
        updateAiMode();
        renderConversation();
        renderAttachmentTray();
        updateInputState();
        hydrateServerHistory();

        elements.sidebarOpen?.addEventListener("click", openSidebar);
        elements.sidebarClose?.addEventListener("click", closeSidebar);
        elements.drawerOverlay?.addEventListener("click", closeSidebar);
        elements.sidebarCollapse?.addEventListener("click", () => setCompactSidebar(!body.classList.contains("ec2-sidebar-compact")));
        elements.newChat?.addEventListener("click", newConversation);

        elements.settingsOpen?.addEventListener("click", openSettings);
        elements.settingsClose?.addEventListener("click", closeSettings);
        elements.settingsOverlay?.addEventListener("click", closeSettings);
        elements.compactToggle?.addEventListener("change", () => setCompactSidebar(elements.compactToggle.checked));
        elements.clearHistory?.addEventListener("click", () => openDeleteDialog(null, "all"));

        elements.exportChat?.addEventListener("click", () => exportConversation());
        elements.exportSettings?.addEventListener("click", () => exportConversation());
        elements.renameActive?.addEventListener("click", () => openRenameDialog(store.state.activeId));
        elements.attachButton?.addEventListener("click", () => elements.attachmentInput?.click());
        elements.attachmentInput?.addEventListener("change", () => uploadAttachment(elements.attachmentInput?.files?.[0]));

        document.querySelectorAll("[data-response-mode]").forEach((button) => {
            button.addEventListener("click", () => setResponseMode(button.dataset.responseMode));
        });
        document.querySelectorAll("[data-settings-mode]").forEach((button) => {
            button.addEventListener("click", () => setResponseMode(button.dataset.settingsMode));
        });

        document.getElementById("ec2SidebarScroll")?.addEventListener("scroll", () => closeHistoryPopovers(), { passive: true });
        elements.historySearch?.addEventListener("input", renderHistory);
        elements.historySearch?.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                elements.historySearch.value = "";
                renderHistory();
                elements.historySearch.blur();
            }
        });

        elements.composer?.addEventListener("submit", (event) => {
            event.preventDefault();
            if (requestInFlight) {
                stopGeneration();
                return;
            }
            sendQuestion(elements.input?.value || "");
        });

        elements.input?.addEventListener("input", updateInputState);
        elements.input?.addEventListener("focus", () => {
            body.classList.add("ec3-composer-focused");
            window.setTimeout(() => {
                scheduleViewportSync();
                scrollToBottom("auto");
            }, 80);
        });
        elements.input?.addEventListener("blur", () => {
            body.classList.remove("ec3-composer-focused");
            window.setTimeout(scheduleViewportSync, 140);
        });
        elements.input?.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
                event.preventDefault();
                if (requestInFlight) stopGeneration();
                else sendQuestion(elements.input.value);
            }
            if (event.key === "Escape") closeCommandMenu();
        });

        elements.commandButton?.addEventListener("click", () => {
            const open = !elements.commandMenu?.hidden;
            elements.commandButton.classList.toggle("is-active", !open);
            if (open) closeCommandMenu(); else openCommandMenu();
            elements.input?.focus();
        });

        elements.jumpBottom?.addEventListener("click", () => scrollToBottom("smooth"));
        elements.thread?.addEventListener("scroll", () => {
            elements.jumpBottom?.classList.toggle("is-visible", !isNearBottom());
        }, { passive: true });

        elements.renameInput?.addEventListener("focus", () => window.setTimeout(scheduleViewportSync, 70));
        elements.renameInput?.addEventListener("blur", () => window.setTimeout(scheduleViewportSync, 120));

        elements.renameForm?.addEventListener("submit", async (event) => {
            event.preventDefault();
            const title = elements.renameInput?.value.trim() || "";
            if (!renameTargetId || !title) return;
            const conversationId = renameTargetId;
            store.rename(conversationId, title);
            await serverJson(`${config.conversationsUrl}/${encodeURIComponent(conversationId)}`, {
                method: "PATCH",
                body: JSON.stringify({ title }),
            });
            elements.renameDialog?.close();
            renameTargetId = null;
            renderConversation({ preserveScroll: true });
            showToast("Назву оновлено", "success");
        });

        elements.deleteForm?.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (deleteScope === "all") {
                const remote = await serverJson(config.conversationsUrl);
                if (remote?.conversations?.length) {
                    await Promise.all(remote.conversations.map((conversation) => serverJson(
                        `${config.conversationsUrl}/${encodeURIComponent(conversation.id)}`,
                        { method: "DELETE" },
                    )));
                }
                store.clearAll();
                showToast("Історію очищено", "success");
            } else if (deleteTargetId) {
                const conversationId = deleteTargetId;
                store.delete(conversationId);
                await serverJson(`${config.conversationsUrl}/${encodeURIComponent(conversationId)}`, { method: "DELETE" });
                showToast("Розмову видалено", "success");
            }
            elements.deleteDialog?.close();
            deleteTargetId = null;
            deleteScope = "conversation";
            renderConversation();
        });

        document.querySelectorAll("[data-dialog-cancel]").forEach((button) => {
            button.addEventListener("click", () => button.closest("dialog")?.close());
        });

        [elements.renameDialog, elements.deleteDialog].filter(Boolean).forEach((dialog) => {
            dialog.addEventListener("close", () => {
                if (!elements.renameDialog?.open && !elements.deleteDialog?.open) body.classList.remove("ec3-dialog-open");
                window.setTimeout(scheduleViewportSync, 80);
            });
            dialog.addEventListener("click", (event) => {
                if (event.target !== dialog) return;
                const rect = dialog.getBoundingClientRect();
                const inside = event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom;
                if (!inside) dialog.close();
            });
        });

        document.addEventListener("click", (event) => {
            const removeAttachment = event.target.closest("[data-remove-attachment]");
            if (removeAttachment && app.contains(removeAttachment)) {
                const attachmentId = removeAttachment.dataset.removeAttachment;
                pendingAttachments = pendingAttachments.filter((item) => item.id !== attachmentId);
                renderAttachmentTray();
                return;
            }

            const starter = event.target.closest("[data-starter-prompt]");
            if (starter && app.contains(starter)) {
                sendQuestion(starter.dataset.starterPrompt || "");
                return;
            }

            const command = event.target.closest("[data-command]");
            if (command && app.contains(command)) {
                chooseCommand(command.dataset.command);
                return;
            }

            const openConversation = event.target.closest("[data-open-conversation]");
            if (openConversation && app.contains(openConversation)) {
                stopGeneration();
                store.setActive(openConversation.dataset.openConversation);
                renderConversation();
                closeSidebar();
                closeHistoryPopovers();
                return;
            }

            const menuButton = event.target.closest("[data-history-menu]");
            if (menuButton && app.contains(menuButton)) {
                event.stopPropagation();
                const id = menuButton.dataset.historyMenu;
                const popover = document.querySelector(`[data-history-popover="${CSS.escape(id)}"]`);
                const shouldOpen = !popover?.classList.contains("is-open");
                closeHistoryPopovers(shouldOpen ? id : null);
                if (shouldOpen && popover) {
                    const rect = menuButton.getBoundingClientRect();
                    const popoverWidth = 178;
                    const popoverHeight = 164;
                    const left = Math.max(8, Math.min(window.innerWidth - popoverWidth - 8, rect.right - popoverWidth));
                    const top = Math.max(8, Math.min(window.innerHeight - popoverHeight - 8, rect.bottom + 4));
                    popover.style.left = `${left}px`;
                    popover.style.top = `${top}px`;
                }
                return;
            }

            const historyAction = event.target.closest("[data-history-action]");
            if (historyAction && app.contains(historyAction)) {
                const action = historyAction.dataset.historyAction;
                const id = historyAction.dataset.id;
                closeHistoryPopovers();
                if (action === "rename") openRenameDialog(id);
                if (action === "pin") {
                    const pinned = store.togglePin(id);
                    renderHistory();
                    serverJson(`${config.conversationsUrl}/${encodeURIComponent(id)}`, {
                        method: "PATCH",
                        body: JSON.stringify({ pinned }),
                    });
                }
                if (action === "export") exportConversation(id);
                if (action === "delete") openDeleteDialog(id);
                return;
            }

            const messageAction = event.target.closest("[data-message-action]");
            if (messageAction && app.contains(messageAction)) {
                const messageNode = messageAction.closest("[data-message-id]");
                const messageId = messageNode?.dataset.messageId;
                const action = messageAction.dataset.messageAction;
                if (!messageId) return;
                const message = store.getActive().messages.find((item) => item.id === messageId);
                if (action === "copy") copyText(message?.text || messageNode.querySelector("[data-raw-text]")?.dataset.rawText || "");
                if (action === "regenerate") regenerate(messageId);
                if (action === "feedback-up") handleFeedback(messageId, "up");
                if (action === "feedback-down") handleFeedback(messageId, "down");
                return;
            }

            const copyCode = event.target.closest("[data-copy-code]");
            if (copyCode && app.contains(copyCode)) {
                const code = copyCode.closest(".ec2-code-block")?.querySelector("code")?.textContent || "";
                copyText(code, "Код скопійовано");
                return;
            }

            if (!event.target.closest(".ec2-history-item")) closeHistoryPopovers();
            if (!event.target.closest("#ec2CommandMenu") && !event.target.closest("#ec2CommandButton") && !event.target.closest("#ec2Input")) {
                elements.commandButton?.classList.remove("is-active");
                closeCommandMenu();
            }
        });

        document.addEventListener("keydown", (event) => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
                event.preventDefault();
                newConversation();
            }
            if ((event.ctrlKey || event.metaKey) && event.key === "/") {
                event.preventDefault();
                openSidebar();
                window.setTimeout(() => elements.historySearch?.focus(), 80);
            }
            if (event.key === "Escape") {
                closeHistoryPopovers();
                closeCommandMenu();
                closeSettings();
                closeSidebar();
            }
        });

        window.addEventListener("pageshow", hideGlobalChrome);
        window.addEventListener("resize", scheduleViewportSync, { passive: true });
        window.visualViewport?.addEventListener("resize", () => {
            scheduleViewportSync();
            if (document.activeElement === elements.input) requestAnimationFrame(() => scrollToBottom("auto"));
        }, { passive: true });
        window.visualViewport?.addEventListener("scroll", scheduleViewportSync, { passive: true });
        window.addEventListener("orientationchange", () => window.setTimeout(scheduleViewportSync, 180), { passive: true });
        window.addEventListener("storage", (event) => {
            if (event.key !== config.storageKey) return;
            store.state = store.load();
            store.ensureActiveConversation();
            renderConversation({ preserveScroll: true });
        });
    });
})();
