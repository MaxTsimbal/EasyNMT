"use strict";

(() => {
    const STORAGE_KEY = "easynmtPageTransition";
    const LOADER_DELAY_MS = 50;
    const body = document.body;

    if (!body) return;

    const routeOrder = [
        "/dashboard", "/today", "/library", "/progress", "/mistakes",
        "/tutor", "/planner", "/achievements", "/profile", "/settings"
    ];

    const normalizePath = (value) => {
        try {
            const url = new URL(value, window.location.href);
            return url.pathname.replace(/\/+$/, "") || "/";
        } catch {
            return "/";
        }
    };

    const routeIndex = (path) => {
        const normalized = normalizePath(path);
        return routeOrder.findIndex((route) => normalized === route || normalized.startsWith(`${route}/`));
    };

    const allowedTypes = new Set(["enter", "exit", "left", "right", "soft"]);

    const saveTransition = (type) => {
        try {
            window.sessionStorage.setItem(STORAGE_KEY, type);
        } catch {
            /* Storage can be disabled without affecting navigation. */
        }
    };

    const inferTransition = (destination, element) => {
        const explicit = element?.dataset?.transition;
        if (allowedTypes.has(explicit)) return explicit;

        const path = normalizePath(destination);
        const currentPath = normalizePath(window.location.href);
        const text = (element?.textContent || "").trim().toLowerCase();

        if (path.includes("logout") || element?.classList?.contains("logout") || text.includes("вийти") || text.includes("назад")) {
            return "exit";
        }

        if (path === currentPath) return "soft";

        const currentIndex = routeIndex(currentPath);
        const nextIndex = routeIndex(path);
        if (currentIndex >= 0 && nextIndex >= 0) {
            return nextIndex > currentIndex ? "left" : "right";
        }

        if (path === "/" || path.includes("login") || path.includes("register")) return "exit";
        return "enter";
    };

    let loaderTimer = 0;
    let lessonProgressTimer = 0;
    let lessonStartedAt = 0;

    const loaderParts = () => ({
        loader: document.getElementById("pageLoader"),
        title: document.getElementById("pageLoaderTitle"),
        message: document.getElementById("pageLoaderMessage"),
        status: document.getElementById("lessonGenerationStatus"),
        topic: document.getElementById("lessonGenerationTopic"),
        hint: document.getElementById("lessonGenerationHint"),
        fill: document.getElementById("pageLoaderProgressFill")
    });

    const lessonRoutePattern = /^\/curriculum\/units\/[^/]+\/(?:start|lesson)$/;

    const elementLessonTitle = (element) => {
        const explicit = element?.dataset?.lessonTitle || element?.closest?.("[data-lesson-title]")?.dataset?.lessonTitle;
        if (explicit?.trim()) return explicit.trim();

        const directTitleNode = element?.querySelector?.("h2, .mini-lesson-title, .level-copy h2, strong, .score");
        if (directTitleNode?.textContent?.trim()) {
            return directTitleNode.textContent.replace(/^○\s*/, "").trim();
        }

        const container = element?.closest?.(
            ".dashboard-clean-next, .level-card, .mini-lesson-row, .planner-row, .dashboard-level-card, .goal-card"
        );
        const titleNode = container?.querySelector?.("h2, .mini-lesson-title, strong, .score");
        return titleNode?.textContent?.replace(/^○\s*/, "").trim() || "";
    };

    const isLessonNavigation = (destination, element) => {
        if (element?.dataset?.lessonLoading !== undefined || element?.closest?.("[data-lesson-loading]")) {
            return true;
        }

        const path = normalizePath(destination);
        if (lessonRoutePattern.test(path)) return true;

        if (element instanceof HTMLFormElement) {
            return Boolean(element.querySelector("input[name='curriculum_unit_id']"));
        }

        return false;
    };

    const resetLessonLoader = () => {
        window.clearInterval(lessonProgressTimer);
        lessonProgressTimer = 0;
        lessonStartedAt = 0;

        const { loader, title, message, status, topic, hint, fill } = loaderParts();
        loader?.classList.remove("lesson-generation-mode");
        if (title) title.innerHTML = "Завантажуємо Easy<span>NMT</span>";
        if (message) message.textContent = "Готуємо для тебе найкращий досвід…";
        if (status) status.hidden = true;
        if (topic) topic.textContent = "";
        if (hint) hint.textContent = "Зазвичай це займає 20–30 секунд.";
        if (fill) {
            fill.style.width = "";
            fill.style.transform = "";
        }
        loader?.querySelectorAll("[data-loader-step]").forEach((step) => {
            step.classList.remove("is-active", "is-complete");
        });
    };

    const updateLessonLoader = () => {
        const { loader, message, hint, fill } = loaderParts();
        if (!loader?.classList.contains("lesson-generation-mode") || !lessonStartedAt) return;

        const elapsedSeconds = Math.max(0, (Date.now() - lessonStartedAt) / 1000);
        const stepIndex = elapsedSeconds < 7 ? 0 : elapsedSeconds < 20 ? 1 : 2;
        const messages = [
            "Easy аналізує тему та підлаштовує урок під твій маршрут.",
            "Збираємо зрозуміле пояснення, приклади й типові помилки.",
            "Фінально перевіряємо структуру уроку перед показом."
        ];

        if (message) message.textContent = messages[stepIndex];

        loader.querySelectorAll("[data-loader-step]").forEach((step, index) => {
            step.classList.toggle("is-complete", index < stepIndex);
            step.classList.toggle("is-active", index === stepIndex);
        });

        // This is intentionally an estimated visual indicator, not a fake exact percentage.
        const estimatedProgress = Math.min(92, 12 + elapsedSeconds * 2.65);
        if (fill) fill.style.width = `${estimatedProgress}%`;

        if (hint) {
            if (elapsedSeconds < 30) {
                hint.textContent = "Зазвичай це займає 20–30 секунд. Сторінка працює, не закривай її.";
            } else if (elapsedSeconds < 50) {
                hint.textContent = "Урок майже готовий. Іноді генерація займає трохи довше.";
            } else {
                hint.textContent = "Easy ще працює над уроком. Дочекайся завершення й не натискай кнопку повторно.";
            }
        }
    };

    const prepareLessonLoader = (element) => {
        const { loader, title, message, status, topic, fill } = loaderParts();
        if (!loader) return;

        loader.classList.add("lesson-generation-mode");
        if (title) title.textContent = "Створюємо твій урок";
        if (message) message.textContent = "Easy аналізує тему та підлаштовує урок під твій маршрут.";
        if (status) status.hidden = false;

        const lessonTitle = elementLessonTitle(element);
        if (topic) {
            topic.textContent = lessonTitle ? `Тема: ${lessonTitle}` : "Персональний AI-урок";
        }

        loader.querySelectorAll("[data-loader-step]").forEach((step, index) => {
            step.classList.toggle("is-active", index === 0);
            step.classList.remove("is-complete");
        });

        if (fill) {
            fill.style.transform = "none";
            fill.style.width = "12%";
        }

        lessonStartedAt = Date.now();
        window.clearInterval(lessonProgressTimer);
        lessonProgressTimer = window.setInterval(updateLessonLoader, 900);
        updateLessonLoader();
    };

    const showLoader = () => {
        const loader = document.getElementById("pageLoader");
        if (!loader) return;
        loader.classList.remove("hidden");
        loader.setAttribute("aria-hidden", "false");
        body.classList.add("easy-transition-loading");
    };

    const scheduleLoader = () => {
        if (body.classList.contains("easy-chat-v6") || body.classList.contains("tutor-chat-page")) return;
        window.clearTimeout(loaderTimer);
        loaderTimer = window.setTimeout(showLoader, LOADER_DELAY_MS);
    };

    const cancelLoader = () => {
        window.clearTimeout(loaderTimer);
        const loader = document.getElementById("pageLoader");
        loader?.classList.add("hidden");
        loader?.setAttribute("aria-hidden", "true");
        body.classList.remove("easy-transition-loading");
        resetLessonLoader();
    };

    const closeTransientUi = () => {
        document.getElementById("dashboardSidebar")?.classList.remove("open");
        document.getElementById("dashboardSidebarOverlay")?.classList.remove("visible");
        document.getElementById("mainNavigation")?.classList.remove("open");
        document.getElementById("mobileMenuButton")?.classList.remove("active");
        body.classList.remove("dashboard-sidebar-open", "menu-open", "lesson-easy-open");
    };

    document.addEventListener("click", (event) => {
        const interactive = event.target.closest("a[href], button, [role='button'], .goal-card, .subject-card, .dashboard-card, .lesson-card");
        if (interactive) {
            interactive.classList.remove("easy-tap");
            requestAnimationFrame(() => interactive.classList.add("easy-tap"));
            window.setTimeout(() => interactive.classList.remove("easy-tap"), 220);
        }

        const link = event.target.closest("a[href]");
        if (!link || event.defaultPrevented) return;
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        if (link.hasAttribute("download") || link.target === "_blank" || link.dataset.noTransition !== undefined) return;

        const href = link.getAttribute("href");
        if (!href || href.startsWith("#") || href.startsWith("javascript:") || href.startsWith("mailto:") || href.startsWith("tel:")) return;

        let destination;
        try {
            destination = new URL(link.href, window.location.href);
        } catch {
            return;
        }

        if (destination.origin !== window.location.origin || destination.href === window.location.href) return;

        event.preventDefault();
        closeTransientUi();
        saveTransition(inferTransition(destination.href, link));
        resetLessonLoader();
        if (isLessonNavigation(destination.href, link)) prepareLessonLoader(link);
        scheduleLoader();

        // Navigation starts immediately. There is no artificial delay.
        window.location.assign(destination.href);
    });

    document.addEventListener("submit", (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || event.defaultPrevented) return;
        if (form.dataset.noTransition !== undefined || form.target === "_blank" || form.closest(".contextual-easy-panel")) return;

        const submitter = event.submitter;
        const type = submitter?.dataset?.transition || form.dataset.transition || "enter";
        saveTransition(allowedTypes.has(type) ? type : "enter");
        resetLessonLoader();
        if (isLessonNavigation(form.action || window.location.href, form)) prepareLessonLoader(form);
        scheduleLoader();
        // Native validation and submission remain untouched.
    }, true);

    window.addEventListener("pageshow", () => {
        closeTransientUi();
        cancelLoader();
    });

    window.addEventListener("pagehide", () => {
        window.clearTimeout(loaderTimer);
        window.clearInterval(lessonProgressTimer);
    });
})();
