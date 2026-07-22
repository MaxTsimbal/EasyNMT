// Mentory v0.7.3 — shared UI helpers

document.addEventListener("DOMContentLoaded", () => {
    const textareas = document.querySelectorAll("textarea");

    textareas.forEach((area) => {
        area.addEventListener("input", () => {
            area.style.height = "auto";
            area.style.height = `${area.scrollHeight}px`;
        });
    });

    const answers = document.querySelectorAll(".tutor-answer .desc");
    answers.forEach((answer) => {
        const original = answer.textContent.trim();
        if (!original || original.length > 700) return;

        answer.textContent = "";
        let index = 0;

        const type = () => {
            answer.textContent = original.slice(0, index);
            index += 2;
            if (index <= original.length) {
                window.setTimeout(type, 14);
            }
        };

        type();
    });
});
