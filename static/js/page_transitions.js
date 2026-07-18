"use strict";

(() => {
    const STORAGE_KEY = "easynmtPageTransition";
    const DURATION = 360;
    const body = document.body;

    if (!body) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const routeOrder = [
        "/dashboard",
        "/today",
        "/library",
        "/progress",
        "/mistakes",
        "/tutor",
        "/planner",
        "/achievements",
        "/profile",
        "/settings"
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

    const saveTransition = (type) => {
        try {
            window.sessionStorage.setItem(STORAGE_KEY, type);
        } catch {
            /* Storage may be disabled. The transition remains graceful. */
        }
    };

    const consumeTransition = () => {
        try {
            const type = window.sessionStorage.getItem(STORAGE_KEY) || "enter";
            window.sessionStorage.removeItem(STORAGE_KEY);
            return type;
        } catch {
            return "enter";
        }
    };

    const allowedTypes = new Set(["enter", "exit", "left", "right", "soft"]);
    let restoredType = consumeTransition();
    restoredType = allowedTypes.has(restoredType) ? restoredType : "enter";

    if (!reducedMotion) {
        body.classList.add("easy-page-enter", `easy-page-enter-${restoredType}`);
        requestAnimationFrame(() => {
            requestAnimationFrame(() => body.classList.add("easy-page-visible"));
        });
        window.setTimeout(() => {
            body.classList.remove(
                "easy-page-enter",
                "easy-page-enter-enter",
                "easy-page-enter-exit",
                "easy-page-enter-left",
                "easy-page-enter-right",
                "easy-page-enter-soft",
                "easy-page-visible"
            );
        }, 620);
    }

    let navigating = false;

    const revealTransitionLoader = () => {
        const loader = document.getElementById("pageLoader");
        if (!loader) return;
        loader.classList.remove("hidden");
        loader.setAttribute("aria-hidden", "false");
        body.classList.add("easy-transition-loading");
    };

    const closeTransientUi = () => {
        document.getElementById("dashboardSidebar")?.classList.remove("open");
        document.getElementById("dashboardSidebarOverlay")?.classList.remove("visible");
        document.getElementById("mainNavigation")?.classList.remove("open");
        document.getElementById("mobileMenuButton")?.classList.remove("active");
        body.classList.remove("dashboard-sidebar-open", "menu-open", "lesson-easy-open");
    };

    const inferTransition = (destination, element) => {
        const explicit = element?.dataset?.transition;
        if (allowedTypes.has(explicit)) return explicit;

        const path = normalizePath(destination);
        const currentPath = normalizePath(window.location.href);
        const text = (element?.textContent || "").trim().toLowerCase();

        if (
            path.includes("logout") ||
            element?.classList?.contains("logout") ||
            text.includes("вийти") ||
            text.includes("назад")
        ) {
            return "exit";
        }

        if (path === currentPath) return "soft";

        const currentIndex = routeIndex(currentPath);
        const nextIndex = routeIndex(path);
        if (currentIndex >= 0 && nextIndex >= 0) {
            if (nextIndex > currentIndex) return "left";
            if (nextIndex < currentIndex) return "right";
        }

        if (path === "/" || path.includes("login") || path.includes("register")) return "exit";
        return "enter";
    };

    const startExit = (type, navigate) => {
        if (navigating) return;
        navigating = true;
        closeTransientUi();
        saveTransition(type);

        revealTransitionLoader();

        if (reducedMotion) {
            window.setTimeout(navigate, 60);
            return;
        }

        body.classList.add("easy-page-leaving", `easy-page-leave-${type}`);
        window.setTimeout(navigate, DURATION);
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
        if (link.hasAttribute("download") || link.target === "_blank") return;
        if (link.dataset.noTransition !== undefined) return;

        const href = link.getAttribute("href");
        if (!href || href.startsWith("#") || href.startsWith("javascript:") || href.startsWith("mailto:") || href.startsWith("tel:")) return;

        let destination;
        try {
            destination = new URL(link.href, window.location.href);
        } catch {
            return;
        }

        if (destination.origin !== window.location.origin) return;
        if (destination.href === window.location.href) return;

        event.preventDefault();
        const type = inferTransition(destination.href, link);
        startExit(type, () => window.location.assign(destination.href));
    });

    document.addEventListener("submit", (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || event.defaultPrevented) return;
        if (form.dataset.noTransition !== undefined || form.target === "_blank") return;

        const submitter = event.submitter;
        const type = submitter?.dataset?.transition || form.dataset.transition || "enter";
        saveTransition(allowedTypes.has(type) ? type : "enter");

        revealTransitionLoader();
        if (!reducedMotion) {
            body.classList.add("easy-page-leaving", `easy-page-leave-${allowedTypes.has(type) ? type : "enter"}`);
        }
        // Do not prevent submission: validation, uploads and POST requests stay native.
    }, true);

    window.addEventListener("pageshow", (event) => {
        closeTransientUi();
        if (event.persisted) {
            navigating = false;
            body.classList.remove(
                "easy-page-leaving",
                "easy-page-leave-enter",
                "easy-page-leave-exit",
                "easy-page-leave-left",
                "easy-page-leave-right",
                "easy-page-leave-soft",
                "easy-transition-loading"
            );
            const loader = document.getElementById("pageLoader");
            loader?.classList.add("hidden");
            loader?.setAttribute("aria-hidden", "true");
        }
    });
})();
