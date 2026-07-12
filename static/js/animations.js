// EasyNMT v0.7.3 — smooth page transitions and card entrance

document.addEventListener("DOMContentLoaded", () => {
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    document.body.classList.add("page-ready");

    if (!prefersReducedMotion) {
        const animatedItems = document.querySelectorAll(
            ".goal-card, .lesson-card, .auth-card, .loader-card, .lesson-section, .tutor-panel, .tutor-answer, .stat-card, .learning-panel, .review-item"
        );

        animatedItems.forEach((item, index) => {
            item.style.animationDelay = `${Math.min(index * 0.055, 0.45)}s`;
            item.classList.add("smooth-card");
        });
    }

    document.querySelectorAll("a[href]").forEach((link) => {
        link.addEventListener("click", (event) => {
            const href = link.getAttribute("href");
            const target = link.getAttribute("target");
            const download = link.hasAttribute("download");

            if (
                prefersReducedMotion ||
                !href ||
                href.startsWith("#") ||
                href.startsWith("http") ||
                href.startsWith("mailto:") ||
                href.startsWith("tel:") ||
                target === "_blank" ||
                download
            ) {
                return;
            }

            event.preventDefault();
            document.body.classList.remove("page-ready");
            document.body.classList.add("page-leaving");

            window.setTimeout(() => {
                window.location.href = href;
            }, 220);
        });
    });
});

// Cosmic Tutor: subtle pointer parallax without affecting usability.
(() => {
    const scene = document.querySelector('.cosmic-scene');
    if (!scene || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    window.addEventListener('pointermove', (event) => {
        const x = (event.clientX / window.innerWidth - 0.5) * 8;
        const y = (event.clientY / window.innerHeight - 0.5) * 8;
        scene.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    }, { passive: true });
})();
