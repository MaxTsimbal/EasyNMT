(() => {
    "use strict";

    const escapeHtml = (value) => String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");

    const inline = (source) => {
        let value = escapeHtml(source);
        const codeTokens = [];
        value = value.replace(/`([^`]+)`/g, (_, code) => {
            const token = `@@EC2INLINE${codeTokens.length}@@`;
            codeTokens.push(`<code>${code}</code>`);
            return token;
        });

        value = value
            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
            .replace(/__([^_]+)__/g, "<strong>$1</strong>")
            .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
            .replace(/~~([^~]+)~~/g, "<del>$1</del>")
            .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
            .replace(/\$([^$\n]+)\$/g, '<span class="ec2-inline-math">\\($1\\)</span>');

        codeTokens.forEach((html, index) => {
            value = value.replace(`@@EC2INLINE${index}@@`, html);
        });
        return value;
    };

    const isTableDivider = (line) => /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
    const splitTableRow = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());

    const render = (source) => {
        const text = String(source ?? "").replace(/\r\n?/g, "\n").trim();
        if (!text) return "";

        const codeBlocks = [];
        const protectedText = text.replace(/```([\w+-]*)\n?([\s\S]*?)```/g, (_, language, code) => {
            const token = `@@EC2CODE${codeBlocks.length}@@`;
            codeBlocks.push({ language: escapeHtml(language || "code"), code: escapeHtml(code.trimEnd()) });
            return token;
        });

        const lines = protectedText.split("\n");
        const output = [];
        let paragraph = [];
        let listType = null;
        let listItems = [];

        const flushParagraph = () => {
            if (!paragraph.length) return;
            output.push(`<p>${inline(paragraph.join(" "))}</p>`);
            paragraph = [];
        };

        const flushList = () => {
            if (!listType || !listItems.length) return;
            output.push(`<${listType}>${listItems.map((item) => `<li>${inline(item)}</li>`).join("")}</${listType}>`);
            listType = null;
            listItems = [];
        };

        for (let index = 0; index < lines.length; index += 1) {
            const raw = lines[index];
            const line = raw.trimEnd();
            const trimmed = line.trim();

            if (!trimmed) {
                flushParagraph();
                flushList();
                continue;
            }

            if (/^@@EC2CODE\d+@@$/.test(trimmed)) {
                flushParagraph();
                flushList();
                output.push(trimmed);
                continue;
            }

            if (index + 1 < lines.length && trimmed.includes("|") && isTableDivider(lines[index + 1])) {
                flushParagraph();
                flushList();
                const headers = splitTableRow(trimmed);
                index += 1;
                const rows = [];
                while (index + 1 < lines.length && lines[index + 1].includes("|") && lines[index + 1].trim()) {
                    rows.push(splitTableRow(lines[index + 1]));
                    index += 1;
                }
                output.push(`<div class="ec2-table-wrap"><table><thead><tr>${headers.map((cell) => `<th>${inline(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${headers.map((_, cellIndex) => `<td>${inline(row[cellIndex] || "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
                continue;
            }

            const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
            if (heading) {
                flushParagraph();
                flushList();
                const level = Math.min(4, heading[1].length + 1);
                output.push(`<h${level}>${inline(heading[2])}</h${level}>`);
                continue;
            }

            const quote = trimmed.match(/^>\s?(.*)$/);
            if (quote) {
                flushParagraph();
                flushList();
                output.push(`<blockquote>${inline(quote[1])}</blockquote>`);
                continue;
            }

            if (/^[-*_]{3,}$/.test(trimmed)) {
                flushParagraph();
                flushList();
                output.push("<hr>");
                continue;
            }

            const unordered = trimmed.match(/^[-*+]\s+(.+)$/);
            const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
            if (unordered || ordered) {
                flushParagraph();
                const nextType = unordered ? "ul" : "ol";
                if (listType && listType !== nextType) flushList();
                listType = nextType;
                listItems.push((unordered || ordered)[1]);
                continue;
            }

            if (/^\$\$[\s\S]+\$\$$/.test(trimmed)) {
                flushParagraph();
                flushList();
                output.push(`<div class="ec2-display-math">\\[${escapeHtml(trimmed.slice(2, -2))}\\]</div>`);
                continue;
            }

            paragraph.push(trimmed);
        }

        flushParagraph();
        flushList();

        let html = output.join("\n");
        codeBlocks.forEach((block, index) => {
            const codeHtml = `<div class="ec2-code-block"><div class="ec2-code-head"><span>${block.language}</span><button type="button" data-copy-code aria-label="Копіювати код">Копіювати</button></div><pre><code>${block.code}</code></pre></div>`;
            html = html.replace(`@@EC2CODE${index}@@`, codeHtml);
        });
        return html;
    };

    const typesetMath = (element) => {
        if (!element || !window.MathJax?.typesetPromise) return Promise.resolve();
        try {
            window.MathJax.typesetClear?.([element]);
            return window.MathJax.typesetPromise([element]).catch(() => undefined);
        } catch {
            return Promise.resolve();
        }
    };

    window.EasyChatV2Markdown = { render, escapeHtml, typesetMath };
})();
