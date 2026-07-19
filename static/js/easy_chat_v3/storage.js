(() => {
    "use strict";

    const VERSION = 2;
    const MAX_CONVERSATIONS = 30;
    const MAX_MESSAGES = 60;
    const MAX_MESSAGE_LENGTH = 12000;

    const nowIso = () => new Date().toISOString();
    const makeId = (prefix = "ec2") => {
        if (window.crypto?.randomUUID) return `${prefix}-${window.crypto.randomUUID()}`;
        return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    };

    const safeText = (value, max = MAX_MESSAGE_LENGTH) => String(value ?? "").trim().slice(0, max);

    const defaultState = () => ({
        version: VERSION,
        activeId: null,
        conversations: [],
        preferences: {
            responseMode: "explain",
            compactSidebar: false,
        },
    });

    class EasyChatStore {
        constructor(storageKey, context = {}) {
            this.storageKey = storageKey;
            this.context = {
                lessonContext: Boolean(context.lessonContext),
                lessonId: safeText(context.lessonId, 80),
                lessonTitle: safeText(context.lessonTitle, 200),
                subject: safeText(context.subject, 120),
            };
            this.state = this.load();
            this.ensureActiveConversation();
        }

        load() {
            try {
                const parsed = JSON.parse(window.localStorage.getItem(this.storageKey) || "null");
                if (!parsed || typeof parsed !== "object") return defaultState();

                const conversations = Array.isArray(parsed.conversations)
                    ? parsed.conversations.map((item) => this.normalizeConversation(item)).filter(Boolean)
                    : [];

                return {
                    version: VERSION,
                    activeId: safeText(parsed.activeId, 120) || null,
                    conversations: conversations.slice(0, MAX_CONVERSATIONS),
                    preferences: {
                        responseMode: ["explain", "concise", "practice"].includes(parsed.preferences?.responseMode)
                            ? parsed.preferences.responseMode
                            : "explain",
                        compactSidebar: Boolean(parsed.preferences?.compactSidebar),
                    },
                };
            } catch (error) {
                console.warn("Easy Chat storage could not be loaded:", error);
                return defaultState();
            }
        }

        normalizeConversation(item) {
            if (!item || typeof item !== "object") return null;
            const id = safeText(item.id, 120) || makeId("chat");
            const createdAt = safeText(item.createdAt, 60) || nowIso();
            const updatedAt = safeText(item.updatedAt, 60) || createdAt;
            const messages = Array.isArray(item.messages)
                ? item.messages.map((message) => this.normalizeMessage(message)).filter(Boolean).slice(-MAX_MESSAGES)
                : [];

            return {
                id,
                title: safeText(item.title, 90) || "Нова розмова",
                createdAt,
                updatedAt,
                pinned: Boolean(item.pinned),
                context: {
                    lessonContext: Boolean(item.context?.lessonContext),
                    lessonId: safeText(item.context?.lessonId, 80),
                    lessonTitle: safeText(item.context?.lessonTitle, 200),
                    subject: safeText(item.context?.subject, 120),
                },
                messages,
            };
        }

        normalizeMessage(message) {
            if (!message || typeof message !== "object") return null;
            const role = ["user", "assistant"].includes(message.role) ? message.role : null;
            const text = safeText(message.text);
            if (!role || !text) return null;
            return {
                id: safeText(message.id, 120) || makeId("msg"),
                role,
                text,
                createdAt: safeText(message.createdAt, 60) || nowIso(),
                feedback: ["up", "down"].includes(message.feedback) ? message.feedback : null,
            };
        }

        save() {
            this.trim();
            try {
                window.localStorage.setItem(this.storageKey, JSON.stringify(this.state));
            } catch (error) {
                console.warn("Easy Chat storage is unavailable:", error);
            }
            window.dispatchEvent(new CustomEvent("easychat:store-change", { detail: this.snapshot() }));
        }

        trim() {
            this.state.conversations.forEach((conversation) => {
                conversation.messages = conversation.messages.slice(-MAX_MESSAGES);
            });

            this.state.conversations.sort((a, b) => {
                if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
                return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
            });
            this.state.conversations = this.state.conversations.slice(0, MAX_CONVERSATIONS);
        }

        snapshot() {
            return JSON.parse(JSON.stringify(this.state));
        }

        ensureActiveConversation() {
            const active = this.getConversation(this.state.activeId);
            if (active) return active;
            const matching = this.state.conversations.find((item) => this.sameContext(item.context, this.context));
            if (matching) {
                this.state.activeId = matching.id;
                this.save();
                return matching;
            }
            return this.createConversation();
        }

        sameContext(a = {}, b = {}) {
            return Boolean(a.lessonContext) === Boolean(b.lessonContext)
                && safeText(a.lessonId, 80) === safeText(b.lessonId, 80);
        }

        createConversation(overrides = {}) {
            const timestamp = nowIso();
            const conversation = {
                id: makeId("chat"),
                title: safeText(overrides.title, 90) || "Нова розмова",
                createdAt: timestamp,
                updatedAt: timestamp,
                pinned: false,
                context: {
                    ...this.context,
                    ...(overrides.context || {}),
                },
                messages: [],
            };
            this.state.conversations.unshift(conversation);
            this.state.activeId = conversation.id;
            this.save();
            return conversation;
        }

        getActive() {
            return this.getConversation(this.state.activeId) || this.ensureActiveConversation();
        }

        getConversation(id) {
            if (!id) return null;
            return this.state.conversations.find((item) => item.id === id) || null;
        }

        setActive(id) {
            if (!this.getConversation(id)) return null;
            this.state.activeId = id;
            this.save();
            return this.getActive();
        }

        list() {
            this.trim();
            return this.state.conversations;
        }

        addMessage(role, text, conversationId = this.state.activeId) {
            const conversation = this.getConversation(conversationId) || this.getActive();
            const message = this.normalizeMessage({
                id: makeId("msg"),
                role,
                text,
                createdAt: nowIso(),
            });
            if (!message) return null;

            conversation.messages.push(message);
            conversation.updatedAt = nowIso();
            if (role === "user" && (!conversation.title || conversation.title === "Нова розмова")) {
                conversation.title = this.makeTitle(message.text);
            }
            this.save();
            return message;
        }

        updateMessage(messageId, patch = {}, conversationId = this.state.activeId) {
            const conversation = this.getConversation(conversationId);
            if (!conversation) return null;
            const message = conversation.messages.find((item) => item.id === messageId);
            if (!message) return null;
            if (typeof patch.text === "string") message.text = safeText(patch.text);
            if (Object.prototype.hasOwnProperty.call(patch, "feedback")) {
                message.feedback = ["up", "down"].includes(patch.feedback) ? patch.feedback : null;
            }
            conversation.updatedAt = nowIso();
            this.save();
            return message;
        }

        removeMessage(messageId, conversationId = this.state.activeId) {
            const conversation = this.getConversation(conversationId);
            if (!conversation) return false;
            const before = conversation.messages.length;
            conversation.messages = conversation.messages.filter((item) => item.id !== messageId);
            if (conversation.messages.length === before) return false;
            conversation.updatedAt = nowIso();
            this.save();
            return true;
        }

        replaceMessages(messages, conversationId = this.state.activeId) {
            const conversation = this.getConversation(conversationId);
            if (!conversation) return null;
            conversation.messages = (Array.isArray(messages) ? messages : [])
                .map((message) => this.normalizeMessage(message))
                .filter(Boolean)
                .slice(-MAX_MESSAGES);
            conversation.updatedAt = nowIso();
            if (conversation.messages[0]?.role === "user") conversation.title = this.makeTitle(conversation.messages[0].text);
            this.save();
            return conversation;
        }

        rename(id, title) {
            const conversation = this.getConversation(id);
            const nextTitle = safeText(title, 90);
            if (!conversation || !nextTitle) return false;
            conversation.title = nextTitle;
            conversation.updatedAt = nowIso();
            this.save();
            return true;
        }

        togglePin(id) {
            const conversation = this.getConversation(id);
            if (!conversation) return false;
            conversation.pinned = !conversation.pinned;
            conversation.updatedAt = nowIso();
            this.save();
            return conversation.pinned;
        }

        delete(id) {
            const existing = this.getConversation(id);
            if (!existing) return false;
            this.state.conversations = this.state.conversations.filter((item) => item.id !== id);
            if (this.state.activeId === id) {
                this.state.activeId = this.state.conversations[0]?.id || null;
            }
            if (!this.state.activeId) this.createConversation();
            else this.save();
            return true;
        }

        clearAll() {
            this.state = defaultState();
            this.state.preferences.responseMode = "explain";
            this.createConversation();
        }

        getPreference(key, fallback = null) {
            return Object.prototype.hasOwnProperty.call(this.state.preferences, key)
                ? this.state.preferences[key]
                : fallback;
        }

        setPreference(key, value) {
            this.state.preferences[key] = value;
            this.save();
        }

        makeTitle(text) {
            const clean = safeText(text, 180).replace(/\s+/g, " ");
            if (clean.length <= 46) return clean;
            return `${clean.slice(0, 43).trim()}…`;
        }

        exportConversation(id = this.state.activeId) {
            const conversation = this.getConversation(id);
            if (!conversation) return "";
            const header = `# ${conversation.title}\n\n`;
            const body = conversation.messages.map((message) => {
                const author = message.role === "user" ? "Ти" : "Easy";
                return `## ${author}\n\n${message.text}`;
            }).join("\n\n");
            return `${header}${body}\n`;
        }
    }

    window.EasyChatV2Storage = {
        EasyChatStore,
        makeId,
    };
})();
