document.addEventListener('DOMContentLoaded', () => {
    const detailsNodes = document.querySelectorAll('details');
    detailsNodes.forEach((node) => {
        node.addEventListener('toggle', () => {
            if (!node.open) {
                return;
            }
            detailsNodes.forEach((other) => {
                if (other !== node) {
                    other.open = false;
                }
            });
        });
    });
});
