(() => {
    const root = document.querySelector('[data-notebook]');
    if (!root) return;

    const steps = [...root.querySelectorAll('.notebook-step')];
    const prev = document.getElementById('notebook-prev');
    const next = document.getElementById('notebook-next');
    const title = document.getElementById('notebook-step-title');
    const note = document.getElementById('notebook-step-note');
    const current = document.getElementById('notebook-current');
    let index = 0;

    function render() {
        steps.forEach((step, i) => step.classList.toggle('is-visible', i === index));
        const active = steps[index];
        title.textContent = active.querySelector('h3')?.textContent || `Крок ${index + 1}`;
        note.textContent = active.querySelector('.notebook-note')?.textContent.replace('Зверни увагу: ', '') || '';
        current.textContent = String(index + 1);
        prev.disabled = index === 0;
        next.textContent = index === steps.length - 1 ? 'Усе зрозуміло ✓' : 'Наступний крок →';
    }

    prev?.addEventListener('click', () => {
        if (index > 0) { index -= 1; render(); }
    });
    next?.addEventListener('click', () => {
        if (index < steps.length - 1) { index += 1; render(); }
    });

    document.querySelectorAll('.solution-upload input[type="file"]').forEach(input => {
        input.addEventListener('change', () => {
            const label = input.closest('.solution-upload');
            const name = label?.querySelector('.solution-upload-name');
            if (name) name.textContent = input.files?.[0]?.name || 'Фото ще не вибрано';
        });
    });
})();
