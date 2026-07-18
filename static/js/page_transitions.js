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

    const showLoader = () => {
        const loader = document.getElementById("pageLoader");
        if (!loader) return;
        loader.classList.remove("hidden");
        loader.setAttribute("aria-hidden", "false");
        body.classList.add("easy-transition-loading");
    };

    const scheduleLoader = () => {
        window.clearTimeout(loaderTimer);
        loaderTimer = window.setTimeout(showLoader, LOADER_DELAY_MS);
    };

    const cancelLoader = () => {
        window.clearTimeout(loaderTimer);
        const loader = document.getElementById("pageLoader");
        loader?.classList.add("hidden");
        loader?.setAttribute("aria-hidden", "true");
        body.classList.remove("easy-transition-loading");
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
        scheduleLoader();

        // Navigation starts immediately. There is no artificial blue-screen delay.
        window.location.assign(destination.href);
    });

    document.addEventListener("submit", (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || event.defaultPrevented) return;
        if (form.dataset.noTransition !== undefined || form.target === "_blank") return;

        const submitter = event.submitter;
        const type = submitter?.dataset?.transition || form.dataset.transition || "enter";
        saveTransition(allowedTypes.has(type) ? type : "enter");
        scheduleLoader();
        // Native validation and submission remain untouched.
    }, true);

    window.addEventListener("pageshow", () => {
        closeTransientUi();
        cancelLoader();
    });

    window.addEventListener("pagehide", () => window.clearTimeout(loaderTimer));
})();
