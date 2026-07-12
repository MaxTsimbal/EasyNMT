"use strict";

/* ==========================================================================
   EasyNMT v0.9.6 Cosmic Tutor Responsive
   File: static/js/animations.js
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
    const body = document.body;
    const siteHeader = document.getElementById("siteHeader");
    const mobileMenuButton = document.getElementById("mobileMenuButton");
    const mainNavigation = document.getElementById("mainNavigation");
    const pageLoader = document.getElementById("pageLoader");
    const scrollTopButton = document.getElementById("scrollTopButton");
    const currentYear = document.getElementById("currentYear");
    const toastContainer = document.getElementById("toastContainer");

    const prefersReducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    ).matches;

    /* ----------------------------------------------------------------------
       Utilities
       ---------------------------------------------------------------------- */

    const clamp = (value, min, max) => {
        return Math.min(Math.max(value, min), max);
    };

    const debounce = (callback, delay = 150) => {
        let timeoutId;

        return (...args) => {
            window.clearTimeout(timeoutId);

            timeoutId = window.setTimeout(() => {
                callback(...args);
            }, delay);
        };
    };

    const getFocusableElements = (container) => {
        if (!container) {
            return [];
        }

        return Array.from(
            container.querySelectorAll(
                [
                    "a[href]",
                    "button:not([disabled])",
                    "input:not([disabled])",
                    "select:not([disabled])",
                    "textarea:not([disabled])",
                    '[tabindex]:not([tabindex="-1"])'
                ].join(",")
            )
        ).filter((element) => {
            return !element.hasAttribute("hidden");
        });
    };

    const safelyParseJSON = (value, fallback = null) => {
        try {
            return JSON.parse(value);
        } catch {
            return fallback;
        }
    };

    const setStoredValue = (key, value) => {
        try {
            window.localStorage.setItem(key, JSON.stringify(value));
        } catch {
            return;
        }
    };

    const getStoredValue = (key, fallback = null) => {
        try {
            const value = window.localStorage.getItem(key);

            if (value === null) {
                return fallback;
            }

            return safelyParseJSON(value, fallback);
        } catch {
            return fallback;
        }
    };

    /* ----------------------------------------------------------------------
       Current year
       ---------------------------------------------------------------------- */

    if (currentYear) {
        currentYear.textContent = String(new Date().getFullYear());
    }

    /* ----------------------------------------------------------------------
       Page loader
       ---------------------------------------------------------------------- */

    const hidePageLoader = () => {
        if (!pageLoader) {
            return;
        }

        pageLoader.classList.add("hidden");
        pageLoader.setAttribute("aria-hidden", "true");

        window.setTimeout(() => {
            pageLoader.remove();
        }, 650);
    };

    if (document.readyState === "complete") {
        hidePageLoader();
    } else {
        window.addEventListener("load", hidePageLoader, { once: true });

        window.setTimeout(() => {
            hidePageLoader();
        }, 2500);
    }

    /* ----------------------------------------------------------------------
       Sticky header
       ---------------------------------------------------------------------- */

    const updateHeaderState = () => {
        if (!siteHeader) {
            return;
        }

        siteHeader.classList.toggle("scrolled", window.scrollY > 16);
    };

    updateHeaderState();

    window.addEventListener("scroll", updateHeaderState, {
        passive: true
    });

    /* ----------------------------------------------------------------------
       Mobile menu
       ---------------------------------------------------------------------- */

    let lastFocusedElement = null;

    const isMenuOpen = () => {
        return Boolean(
            mainNavigation &&
            mainNavigation.classList.contains("open")
        );
    };

    const openMobileMenu = () => {
        if (!mobileMenuButton || !mainNavigation) {
            return;
        }

        lastFocusedElement = document.activeElement;

        mainNavigation.classList.add("open");
        mobileMenuButton.classList.add("active");
        mobileMenuButton.setAttribute("aria-expanded", "true");
        mobileMenuButton.setAttribute("aria-label", "Закрити меню");
        body.classList.add("menu-open");

        const focusableElements = getFocusableElements(mainNavigation);

        if (focusableElements.length > 0) {
            window.setTimeout(() => {
                focusableElements[0].focus();
            }, 80);
        }
    };

    const closeMobileMenu = ({ returnFocus = true } = {}) => {
        if (!mobileMenuButton || !mainNavigation) {
            return;
        }

        mainNavigation.classList.remove("open");
        mobileMenuButton.classList.remove("active");
        mobileMenuButton.setAttribute("aria-expanded", "false");
        mobileMenuButton.setAttribute("aria-label", "Відкрити меню");
        body.classList.remove("menu-open");

        if (
            returnFocus &&
            lastFocusedElement instanceof HTMLElement
        ) {
            lastFocusedElement.focus();
        }
    };

    const toggleMobileMenu = () => {
        if (isMenuOpen()) {
            closeMobileMenu();
            return;
        }

        openMobileMenu();
    };

    if (mobileMenuButton && mainNavigation) {
        mobileMenuButton.addEventListener("click", toggleMobileMenu);

        mainNavigation.addEventListener("click", (event) => {
            const clickedLink = event.target.closest("a");

            if (!clickedLink) {
                return;
            }

            closeMobileMenu({
                returnFocus: false
            });
        });

        document.addEventListener("click", (event) => {
            if (!isMenuOpen()) {
                return;
            }

            const clickedInsideNavigation =
                mainNavigation.contains(event.target);

            const clickedMenuButton =
                mobileMenuButton.contains(event.target);

            if (!clickedInsideNavigation && !clickedMenuButton) {
                closeMobileMenu({
                    returnFocus: false
                });
            }
        });

        document.addEventListener("keydown", (event) => {
            if (!isMenuOpen()) {
                return;
            }

            if (event.key === "Escape") {
                event.preventDefault();
                closeMobileMenu();
                return;
            }

            if (event.key !== "Tab") {
                return;
            }

            const focusableElements =
                getFocusableElements(mainNavigation);

            if (focusableElements.length === 0) {
                return;
            }

            const firstElement = focusableElements[0];
            const lastElement =
                focusableElements[focusableElements.length - 1];

            if (
                event.shiftKey &&
                document.activeElement === firstElement
            ) {
                event.preventDefault();
                lastElement.focus();
            } else if (
                !event.shiftKey &&
                document.activeElement === lastElement
            ) {
                event.preventDefault();
                firstElement.focus();
            }
        });

        window.addEventListener(
            "resize",
            debounce(() => {
                if (window.innerWidth > 920 && isMenuOpen()) {
                    closeMobileMenu({
                        returnFocus: false
                    });
                }
            }, 120)
        );
    }

    /* ----------------------------------------------------------------------
       Smooth anchor navigation
       ---------------------------------------------------------------------- */

    document.addEventListener("click", (event) => {
        const anchor = event.target.closest('a[href^="#"]');

        if (!anchor) {
            return;
        }

        const targetId = anchor.getAttribute("href");

        if (!targetId || targetId === "#") {
            return;
        }

        const target = document.querySelector(targetId);

        if (!target) {
            return;
        }

        event.preventDefault();

        const headerOffset = siteHeader
            ? siteHeader.offsetHeight + 12
            : 12;

        const targetPosition =
            target.getBoundingClientRect().top +
            window.scrollY -
            headerOffset;

        window.scrollTo({
            top: targetPosition,
            behavior: prefersReducedMotion ? "auto" : "smooth"
        });

        if (target instanceof HTMLElement) {
            target.setAttribute("tabindex", "-1");

            window.setTimeout(() => {
                target.focus({
                    preventScroll: true
                });
            }, prefersReducedMotion ? 0 : 500);
        }
    });

    /* ----------------------------------------------------------------------
       Scroll to top button
       ---------------------------------------------------------------------- */

    const updateScrollTopButton = () => {
        if (!scrollTopButton) {
            return;
        }

        scrollTopButton.classList.toggle(
            "visible",
            window.scrollY > 520
        );
    };

    updateScrollTopButton();

    window.addEventListener("scroll", updateScrollTopButton, {
        passive: true
    });

    if (scrollTopButton) {
        scrollTopButton.addEventListener("click", () => {
            window.scrollTo({
                top: 0,
                behavior: prefersReducedMotion ? "auto" : "smooth"
            });
        });
    }

    /* ----------------------------------------------------------------------
       Reveal animations
       ---------------------------------------------------------------------- */

    const revealElements = document.querySelectorAll(
        [
            ".reveal",
            ".feature-card",
            ".subject-card",
            ".step-card",
            ".pricing-card",
            ".dashboard-card",
            ".option-card"
        ].join(",")
    );

    revealElements.forEach((element, index) => {
        if (!element.classList.contains("reveal")) {
            element.classList.add("reveal");
        }

        element.style.transitionDelay =
            `${Math.min(index % 6, 5) * 70}ms`;
    });

    if (prefersReducedMotion) {
        revealElements.forEach((element) => {
            element.classList.add("visible");
            element.style.transitionDelay = "0ms";
        });
    } else if ("IntersectionObserver" in window) {
        const revealObserver = new IntersectionObserver(
            (entries, observer) => {
                entries.forEach((entry) => {
                    if (!entry.isIntersecting) {
                        return;
                    }

                    entry.target.classList.add("visible");
                    observer.unobserve(entry.target);
                });
            },
            {
                threshold: 0.12,
                rootMargin: "0px 0px -40px 0px"
            }
        );

        revealElements.forEach((element) => {
            revealObserver.observe(element);
        });
    } else {
        revealElements.forEach((element) => {
            element.classList.add("visible");
        });
    }

    /* ----------------------------------------------------------------------
       FAQ accordion
       ---------------------------------------------------------------------- */

    const faqItems = document.querySelectorAll(".faq-item");

    const closeFaqItem = (item) => {
        const question = item.querySelector(".faq-question");
        const answer = item.querySelector(".faq-answer");

        item.classList.remove("open");

        if (question) {
            question.setAttribute("aria-expanded", "false");
        }

        if (answer) {
            answer.style.maxHeight = "0px";
        }
    };

    const openFaqItem = (item) => {
        const question = item.querySelector(".faq-question");
        const answer = item.querySelector(".faq-answer");

        item.classList.add("open");

        if (question) {
            question.setAttribute("aria-expanded", "true");
        }

        if (answer) {
            answer.style.maxHeight = `${answer.scrollHeight}px`;
        }
    };

    faqItems.forEach((item) => {
        const question = item.querySelector(".faq-question");

        if (!question) {
            return;
        }

        question.setAttribute(
            "aria-expanded",
            item.classList.contains("open") ? "true" : "false"
        );

        question.addEventListener("click", () => {
            const shouldOpen = !item.classList.contains("open");

            faqItems.forEach((faqItem) => {
                closeFaqItem(faqItem);
            });

            if (shouldOpen) {
                openFaqItem(item);
            }
        });
    });

    window.addEventListener(
        "resize",
        debounce(() => {
            faqItems.forEach((item) => {
                if (!item.classList.contains("open")) {
                    return;
                }

                const answer = item.querySelector(".faq-answer");

                if (answer) {
                    answer.style.maxHeight =
                        `${answer.scrollHeight}px`;
                }
            });
        }, 130)
    );

    /* ----------------------------------------------------------------------
       Option cards for onboarding
       ---------------------------------------------------------------------- */

    const optionGroups = document.querySelectorAll(
        "[data-option-group]"
    );

    optionGroups.forEach((group) => {
        const groupName =
            group.dataset.optionGroup || "default";

        const allowMultiple =
            group.dataset.multiple === "true";

        const cards = Array.from(
            group.querySelectorAll(".option-card")
        );

        const hiddenInputSelector =
            group.dataset.inputTarget || "";

        const hiddenInput = hiddenInputSelector
            ? document.querySelector(hiddenInputSelector)
            : null;

        const storedValue = getStoredValue(
            `easynmt_option_${groupName}`,
            allowMultiple ? [] : ""
        );

        const updateHiddenInput = () => {
            if (!hiddenInput) {
                return;
            }

            const selectedValues = cards
                .filter((card) => {
                    return card.classList.contains("selected");
                })
                .map((card) => {
                    return card.dataset.value || "";
                })
                .filter(Boolean);

            hiddenInput.value = allowMultiple
                ? selectedValues.join(",")
                : selectedValues[0] || "";

            hiddenInput.dispatchEvent(
                new Event("change", {
                    bubbles: true
                })
            );
        };

        const persistSelection = () => {
            const selectedValues = cards
                .filter((card) => {
                    return card.classList.contains("selected");
                })
                .map((card) => {
                    return card.dataset.value || "";
                })
                .filter(Boolean);

            setStoredValue(
                `easynmt_option_${groupName}`,
                allowMultiple
                    ? selectedValues
                    : selectedValues[0] || ""
            );
        };

        const selectCard = (card) => {
            if (!allowMultiple) {
                cards.forEach((currentCard) => {
                    currentCard.classList.remove("selected");
                    currentCard.setAttribute(
                        "aria-pressed",
                        "false"
                    );
                });
            }

            const willSelect =
                allowMultiple
                    ? !card.classList.contains("selected")
                    : true;

            card.classList.toggle("selected", willSelect);
            card.setAttribute(
                "aria-pressed",
                willSelect ? "true" : "false"
            );

            updateHiddenInput();
            persistSelection();
        };

        cards.forEach((card) => {
            card.setAttribute("role", "button");
            card.setAttribute("tabindex", "0");
            card.setAttribute("aria-pressed", "false");

            const value = card.dataset.value || "";

            const shouldRestore = allowMultiple
                ? Array.isArray(storedValue) &&
                  storedValue.includes(value)
                : storedValue === value;

            if (shouldRestore) {
                card.classList.add("selected");
                card.setAttribute("aria-pressed", "true");
            }

            card.addEventListener("click", () => {
                selectCard(card);
            });

            card.addEventListener("keydown", (event) => {
                if (
                    event.key !== "Enter" &&
                    event.key !== " "
                ) {
                    return;
                }

                event.preventDefault();
                selectCard(card);
            });
        });

        updateHiddenInput();
    });

    /* ----------------------------------------------------------------------
       Form validation helpers
       ---------------------------------------------------------------------- */

    const forms = document.querySelectorAll(
        "form[data-validate]"
    );

    const validateField = (field) => {
        const value = field.value.trim();
        const isRequired = field.hasAttribute("required");
        const pattern = field.getAttribute("pattern");

        let isValid = true;
        let message = "";

        if (isRequired && value.length === 0) {
            isValid = false;
            message = "Заповни це поле.";
        } else if (pattern && value.length > 0) {
            const expression = new RegExp(pattern);

            if (!expression.test(value)) {
                isValid = false;
                message =
                    field.dataset.errorMessage ||
                    "Перевір правильність введених даних.";
            }
        }

        field.classList.toggle("invalid", !isValid);
        field.setAttribute(
            "aria-invalid",
            isValid ? "false" : "true"
        );

        const group = field.closest(".form-group");
        let errorElement = group
            ? group.querySelector(".form-error")
            : null;

        if (!isValid && group) {
            if (!errorElement) {
                errorElement = document.createElement("span");
                errorElement.className = "form-error";
                errorElement.setAttribute("role", "alert");
                group.appendChild(errorElement);
            }

            errorElement.textContent = message;
        } else if (errorElement) {
            errorElement.remove();
        }

        return isValid;
    };

    forms.forEach((form) => {
        const fields = Array.from(
            form.querySelectorAll(
                "input, select, textarea"
            )
        );

        fields.forEach((field) => {
            field.addEventListener("blur", () => {
                validateField(field);
            });

            field.addEventListener("input", () => {
                if (field.classList.contains("invalid")) {
                    validateField(field);
                }
            });
        });

        form.addEventListener("submit", (event) => {
            const results = fields.map((field) => {
                return validateField(field);
            });

            const isValid = results.every(Boolean);

            if (!isValid) {
                event.preventDefault();

                const firstInvalidField =
                    form.querySelector(".invalid");

                if (firstInvalidField) {
                    firstInvalidField.focus();
                }

                showToast(
                    "Перевір поля форми перед продовженням.",
                    "warning"
                );
            }
        });
    });

    /* ----------------------------------------------------------------------
       Toast notifications
       ---------------------------------------------------------------------- */

    function showToast(message, type = "info", duration = 3200) {
        if (!toastContainer || !message) {
            return;
        }

        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        toast.setAttribute("role", "status");

        const toastText = document.createElement("span");
        toastText.textContent = message;

        toast.appendChild(toastText);
        toastContainer.appendChild(toast);

        window.setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(18px)";

            window.setTimeout(() => {
                toast.remove();
            }, 260);
        }, duration);
    }

    window.EasyNMT = {
        showToast,
        getStoredValue,
        setStoredValue
    };

    /* ----------------------------------------------------------------------
       Progress bars
       ---------------------------------------------------------------------- */

    const progressBars = document.querySelectorAll(
        ".progress-bar[data-progress]"
    );

    const animateProgressBar = (bar) => {
        const rawValue = Number(bar.dataset.progress || 0);
        const value = clamp(rawValue, 0, 100);

        bar.style.width = "0%";

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                bar.style.width = `${value}%`;
            });
        });

        bar.setAttribute("aria-valuemin", "0");
        bar.setAttribute("aria-valuemax", "100");
        bar.setAttribute("aria-valuenow", String(value));
    };

    if ("IntersectionObserver" in window) {
        const progressObserver = new IntersectionObserver(
            (entries, observer) => {
                entries.forEach((entry) => {
                    if (!entry.isIntersecting) {
                        return;
                    }

                    animateProgressBar(entry.target);
                    observer.unobserve(entry.target);
                });
            },
            {
                threshold: 0.35
            }
        );

        progressBars.forEach((bar) => {
            progressObserver.observe(bar);
        });
    } else {
        progressBars.forEach((bar) => {
            animateProgressBar(bar);
        });
    }

    /* ----------------------------------------------------------------------
       Counter animation
       ---------------------------------------------------------------------- */

    const counters = document.querySelectorAll(
        "[data-counter]"
    );

    const animateCounter = (element) => {
        const target = Number(element.dataset.counter || 0);
        const duration = Number(
            element.dataset.duration || 1100
        );

        if (
            prefersReducedMotion ||
            !Number.isFinite(target)
        ) {
            element.textContent = String(target);
            return;
        }

        const startTime = performance.now();

        const update = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = clamp(elapsed / duration, 0, 1);
            const eased =
                1 - Math.pow(1 - progress, 3);

            const currentValue = Math.round(
                target * eased
            );

            element.textContent =
                currentValue.toLocaleString("uk-UA");

            if (progress < 1) {
                requestAnimationFrame(update);
            }
        };

        requestAnimationFrame(update);
    };

    if ("IntersectionObserver" in window) {
        const counterObserver = new IntersectionObserver(
            (entries, observer) => {
                entries.forEach((entry) => {
                    if (!entry.isIntersecting) {
                        return;
                    }

                    animateCounter(entry.target);
                    observer.unobserve(entry.target);
                });
            },
            {
                threshold: 0.4
            }
        );

        counters.forEach((counter) => {
            counterObserver.observe(counter);
        });
    } else {
        counters.forEach((counter) => {
            animateCounter(counter);
        });
    }

    /* ----------------------------------------------------------------------
       Parallax for hero cards
       ---------------------------------------------------------------------- */

    const parallaxElements = document.querySelectorAll(
        "[data-parallax]"
    );

    if (
        !prefersReducedMotion &&
        parallaxElements.length > 0
    ) {
        const updateParallax = () => {
            const viewportCenter =
                window.innerHeight / 2;

            parallaxElements.forEach((element) => {
                const speed = Number(
                    element.dataset.parallax || 0.08
                );

                const rect =
                    element.getBoundingClientRect();

                const elementCenter =
                    rect.top + rect.height / 2;

                const distance =
                    elementCenter - viewportCenter;

                const offset = clamp(
                    distance * speed,
                    -28,
                    28
                );

                element.style.transform =
                    `translate3d(0, ${offset}px, 0)`;
            });
        };

        updateParallax();

        window.addEventListener("scroll", updateParallax, {
            passive: true
        });

        window.addEventListener(
            "resize",
            debounce(updateParallax, 100)
        );
    }

    /* ----------------------------------------------------------------------
       Magnetic button effect
       ---------------------------------------------------------------------- */

    const magneticButtons = document.querySelectorAll(
        "[data-magnetic]"
    );

    if (
        !prefersReducedMotion &&
        window.matchMedia("(hover: hover)").matches
    ) {
        magneticButtons.forEach((button) => {
            button.addEventListener("mousemove", (event) => {
                const rect =
                    button.getBoundingClientRect();

                const offsetX =
                    event.clientX -
                    rect.left -
                    rect.width / 2;

                const offsetY =
                    event.clientY -
                    rect.top -
                    rect.height / 2;

                button.style.transform =
                    `translate(${offsetX * 0.1}px, ${offsetY * 0.1}px)`;
            });

            button.addEventListener("mouseleave", () => {
                button.style.transform = "";
            });
        });
    }

    /* ----------------------------------------------------------------------
       Active navigation section
       ---------------------------------------------------------------------- */

    const navigationLinks = Array.from(
        document.querySelectorAll(
            '.navigation-link[href*="#"]'
        )
    );

    const observedSections = navigationLinks
        .map((link) => {
            const href = link.getAttribute("href") || "";
            const hashIndex = href.indexOf("#");

            if (hashIndex === -1) {
                return null;
            }

            const hash = href.slice(hashIndex);

            if (!hash || hash === "#") {
                return null;
            }

            const section = document.querySelector(hash);

            if (!section) {
                return null;
            }

            return {
                link,
                section
            };
        })
        .filter(Boolean);

    if (
        observedSections.length > 0 &&
        "IntersectionObserver" in window
    ) {
        const sectionObserver = new IntersectionObserver(
            (entries) => {
                const visibleEntries = entries
                    .filter((entry) => entry.isIntersecting)
                    .sort((a, b) => {
                        return b.intersectionRatio -
                            a.intersectionRatio;
                    });

                if (visibleEntries.length === 0) {
                    return;
                }

                const activeId =
                    visibleEntries[0].target.id;

                observedSections.forEach(
                    ({ link, section }) => {
                        link.classList.toggle(
                            "active",
                            section.id === activeId
                        );
                    }
                );
            },
            {
                rootMargin: "-30% 0px -55% 0px",
                threshold: [0.1, 0.3, 0.6]
            }
        );

        observedSections.forEach(({ section }) => {
            sectionObserver.observe(section);
        });
    }

    /* ----------------------------------------------------------------------
       Page transition for internal links
       ---------------------------------------------------------------------- */

    const shouldUsePageTransition = (link) => {
        if (!link) {
            return false;
        }

        const href = link.getAttribute("href");

        if (
            !href ||
            href.startsWith("#") ||
            href.startsWith("mailto:") ||
            href.startsWith("tel:") ||
            link.hasAttribute("download") ||
            link.target === "_blank"
        ) {
            return false;
        }

        let destination;

        try {
            destination = new URL(
                href,
                window.location.href
            );
        } catch {
            return false;
        }

        return (
            destination.origin ===
            window.location.origin
        );
    };

    document.addEventListener("click", (event) => {
        const link = event.target.closest("a");

        if (
            !link ||
            event.defaultPrevented ||
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey ||
            !shouldUsePageTransition(link)
        ) {
            return;
        }

        const destination = link.href;

        if (
            destination === window.location.href
        ) {
            return;
        }

        if (prefersReducedMotion) {
            return;
        }

        event.preventDefault();
        body.classList.add("page-leaving");

        window.setTimeout(() => {
            window.location.href = destination;
        }, 180);
    });

    /* ----------------------------------------------------------------------
       Restore state when returning from browser cache
       ---------------------------------------------------------------------- */

    window.addEventListener("pageshow", (event) => {
        if (event.persisted) {
            body.classList.remove("page-leaving");
            hidePageLoader();
        }
    });

    /* ----------------------------------------------------------------------
       Keyboard focus styling
       ---------------------------------------------------------------------- */

    const handleFirstTab = (event) => {
        if (event.key !== "Tab") {
            return;
        }

        body.classList.add("keyboard-user");
        window.removeEventListener(
            "keydown",
            handleFirstTab
        );
    };

    window.addEventListener(
        "keydown",
        handleFirstTab
    );

    /* ----------------------------------------------------------------------
       Initial ready state
       ---------------------------------------------------------------------- */

    requestAnimationFrame(() => {
        body.classList.add("page-ready");
    });
});

/* EasyNMT v0.9.8 Liquid Glass dashboard controls */
document.addEventListener("DOMContentLoaded", () => {
    const body = document.body;
    const toggle = document.getElementById("dashboardSidebarToggle");
    const sidebar = document.getElementById("dashboardSidebar");
    const overlay = document.getElementById("dashboardSidebarOverlay");

    if (!toggle || !sidebar || !overlay) {
        return;
    }

    const closeSidebar = () => {
        sidebar.classList.remove("open");
        overlay.classList.remove("visible");
        body.classList.remove("dashboard-sidebar-open");
        toggle.setAttribute("aria-expanded", "false");
        overlay.setAttribute("aria-hidden", "true");
    };

    const openSidebar = () => {
        sidebar.classList.add("open");
        overlay.classList.add("visible");
        body.classList.add("dashboard-sidebar-open");
        toggle.setAttribute("aria-expanded", "true");
        overlay.setAttribute("aria-hidden", "false");

        const firstLink = sidebar.querySelector("a, button");
        if (firstLink) {
            window.setTimeout(() => firstLink.focus(), 80);
        }
    };

    toggle.addEventListener("click", () => {
        if (sidebar.classList.contains("open")) {
            closeSidebar();
        } else {
            openSidebar();
        }
    });

    overlay.addEventListener("click", closeSidebar);

    sidebar.addEventListener("click", (event) => {
        if (event.target.closest("a")) {
            closeSidebar();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && sidebar.classList.contains("open")) {
            closeSidebar();
            toggle.focus();
        }
    });

    window.addEventListener("resize", () => {
        if (window.innerWidth > 920) {
            closeSidebar();
        }
    });
});
