document.addEventListener('DOMContentLoaded', () => {
    const tabs = document.querySelectorAll('.mosaic-tab');
    const panes = document.querySelectorAll('.tab-pane');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Remove active class from all tabs and panes
            tabs.forEach(t => t.classList.remove('active'));
            panes.forEach(p => {
                p.classList.remove('active');
                p.classList.remove('fade-in'); // Reset animation
            });

            // Add active class to clicked tab
            tab.classList.add('active');

            // Show corresponding pane
            const targetId = tab.getAttribute('data-target');
            const targetPane = document.getElementById(targetId);
            if (targetPane) {
                targetPane.classList.add('active');
                // Trigger reflow to restart animation
                void targetPane.offsetWidth;
                targetPane.classList.add('fade-in');
            }
        });
    });
});
